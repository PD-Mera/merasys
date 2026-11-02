import argparse
import logging
from datetime import timedelta

from sqlalchemy import delete, select

from .db import ComposeService, Health, Outbox, Sample, Target, initialize, now
from .settings import Settings, LiveSessions


def main():
    parser = argparse.ArgumentParser(description="Google Sheet / Agent / Docker monitor")
    parser.add_argument("command", choices=["init-db", "sync-once", "collector", "alerts", "web", "prune", "forget-compose-service", "rabbitmq", "rabbitmq-once", "reset-password"])
    parser.add_argument("--days", type=int, default=7, help="Sample retention for prune (default: 7)")
    parser.add_argument("--host", help="Server IP for forget-compose-service")
    parser.add_argument("--compose", help="Compose project for forget-compose-service")
    parser.add_argument("--service", help="Service intentionally removed from Compose")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = Settings.load()
    sessions = LiveSessions(settings)
    if args.command == "reset-password":
        from getpass import getpass
        from .control import reset_password
        password = getpass("Mật khẩu mới: ")
        if not 1 <= len(password) <= 256 or password != getpass("Nhập lại: "):
            raise SystemExit("Mật khẩu không hợp lệ hoặc không khớp")
        reset_password(password)
        print("Đã đổi mật khẩu và kết thúc mọi phiên đăng nhập; cấu hình được giữ nguyên")
    elif args.command == "init-db":
        if not settings.ready:
            print("Chưa cấu hình DB; mở web để đăng ký và thiết lập PostgreSQL")
            return
        initialize(sessions.engine)
        with sessions.begin() as session:
            for name in ("sheet", "alert-worker", "rabbitmq-worker"):
                if session.get(Health, name) is None:
                    session.add(Health(name=name, last_attempt_at=now()))
        with sessions.begin() as session:
            session.execute(delete(Health).where(Health.name == "collector"))
            from .availability import initialize_history
            initialize_history(session, settings.stale_after_seconds)
        print("Database initialized")
    elif args.command in {"sync-once", "collector"}:
        from .collector import run
        from .sheet import sync_sheet
        if args.command == "sync-once":
            if not settings.sheet_ready:
                raise SystemExit("Mở web → Cấu hình để nhập PostgreSQL và Google Sheet trước")
            sync_sheet(settings, sessions)
        else:
            run(settings, sessions)
    elif args.command in {"rabbitmq", "rabbitmq-once"}:
        from .rabbitmq import run, check_once
        (check_once if args.command == "rabbitmq-once" else run)(settings, sessions)
    elif args.command == "alerts":
        from .alerts import run
        run(settings, sessions)
    elif args.command == "web":
        import uvicorn
        from .web import create_app
        uvicorn.run(create_app(settings, sessions), host=settings.web_host, port=settings.web_port)
    elif args.command == "prune":
        if not settings.ready:
            print("Chưa cấu hình DB; bỏ qua prune")
            return
        if args.days < 1:
            parser.error("--days must be positive")
        cutoff = now() - timedelta(days=args.days)
        notification_cutoff = now() - timedelta(days=30)
        with sessions.begin() as session:
            session.execute(delete(Sample).where(Sample.checked_at < cutoff))
            session.execute(delete(Outbox).where(Outbox.sent_at.is_not(None), Outbox.sent_at < notification_cutoff))
            from .availability import prune
            prune(session)
    elif args.command == "forget-compose-service":
        if not all((args.host, args.compose, args.service)):
            parser.error("forget-compose-service requires --host, --compose, --service")
        with sessions.begin() as session:
            target = session.scalar(select(Target).where(Target.host == args.host, Target.container == "compose:" + args.compose))
            if target is None:
                parser.error("Compose target not found")
            result = session.execute(delete(ComposeService).where(ComposeService.target_id == target.id, ComposeService.name == args.service))
            print(f"Removed {result.rowcount} remembered service(s); next successful collection reevaluates Compose")


if __name__ == "__main__":
    main()
