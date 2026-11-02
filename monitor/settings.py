import os
import threading
import time

from dotenv import load_dotenv

from . import control

DEFAULTS = {
    "database_url": "", "google_credentials_info": {}, "google_sheet_id": "", "google_worksheet": "Monitoring",
    "sheet_sync_seconds": 60, "failure_threshold": 3, "recovery_threshold": 2, "stale_after_seconds": 180,
    "alert_poll_seconds": 15, "alert_reminder_seconds": 0, "sheet_stale_after_seconds": 600,
    "telegram_bot_token": "", "telegram_chat_id": "", "telegram_message_thread_id": None,
    "display_timezone": "Asia/Bangkok", "agent_tokens": {}, "rabbitmq_poll_seconds": 60,
}
SECRET_KEYS = {"database_url", "google_credentials_info", "telegram_bot_token", "agent_tokens"}


class Settings:
    def __init__(self, host, port):
        self.web_host, self.web_port = host, port
        self._cached, self._cached_at = {}, 0
        self._lock = threading.RLock()

    @classmethod
    def load(cls):
        control.initialize()
        load_dotenv(".env")
        port = int(os.getenv("WEB_PORT", "21707"))
        if not 1 <= port <= 65535:
            raise ValueError("WEB_PORT must be between 1 and 65535")
        return cls(os.getenv("WEB_HOST", "0.0.0.0"), port)

    def reload(self):
        with self._lock:
            self._cached = {**DEFAULTS, **control.configuration()}
            self._cached_at = time.monotonic()
            return self._cached.copy()

    def __getattr__(self, name):
        if name not in DEFAULTS:
            raise AttributeError(name)
        with self._lock:
            if time.monotonic() - self._cached_at >= 0.5:
                self.reload()
            return self._cached.get(name, DEFAULTS[name])

    def wait(self, seconds):
        baseline = self.reload()
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            time.sleep(min(1, max(0, deadline - time.monotonic())))
            if self.reload() != baseline:
                return

    @property
    def ready(self):
        return bool(self.database_url)

    @property
    def sheet_ready(self):
        return self.ready and bool(self.google_credentials_info and self.google_sheet_id)


class LiveSessions:
    """Reconnect workers to the selected PostgreSQL database without a restart."""
    def __init__(self, settings):
        self.settings = settings
        self._url, self._engine, self._sessions = None, None, None
        self._lock = threading.RLock()

    def factory(self):
        from .db import connect
        url = self.settings.database_url
        if not url:
            raise ValueError("Chưa cấu hình PostgreSQL; mở giao diện Cấu hình")
        with self._lock:
            if self._url != url:
                engine, sessions = connect(url)
                if self._engine:
                    self._engine.dispose()
                self._url, self._engine, self._sessions = url, engine, sessions
            return self._sessions

    @property
    def engine(self):
        self.factory()
        return self._engine

    def __call__(self):
        return self.factory()()

    def begin(self):
        return self.factory().begin()
