import json
from uuid import uuid4
from datetime import timedelta
from urllib.parse import quote, urlsplit

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text, update

from .db import ComposeService, Health, Incident, Outbox, Target, now


class ArchiveRequest(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=200)


class TestAlertRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=2000)
    owners: list[str] = Field(default_factory=list, max_length=20)


def create_app(settings, sessions):
    app = FastAPI(title="Merasys", docs_url=None, redoc_url=None, openapi_url=None)
    from .setup_web import attach, authorize
    from .frontend import attach_assets, page
    from . import control
    attach(app, settings)
    attach_assets(app)
    from .agent_install import attach as attach_agent_install
    attach_agent_install(app)
    from .ingest import router
    app.include_router(router(settings, sessions))

    def snapshot():
        with sessions() as session:
            stamp = now()
            targets = []
            members = {}
            for member in session.scalars(select(ComposeService).order_by(ComposeService.name)):
                members.setdefault(member.target_id, []).append(member)
            for t in session.scalars(select(Target).where(Target.archived.is_(False)).order_by(Target.host, Target.container)):
                state = t.status
                if not t.enabled:
                    state = "DISABLED"
                elif not t.checked_at or stamp - t.checked_at > timedelta(seconds=settings.stale_after_seconds):
                    state = "UNKNOWN"
                targets.append({"id": t.id, "host": t.host, "container": t.container or "(server)", "display_name": t.display_name, "projects": t.projects,
                                "owners": t.owners, "note": t.note, "status": state, "reason": t.reason, "rabbitmq": t.rabbitmq or {}, "rabbitmq_metrics": t.rabbitmq_metrics or {},
                                "server_config": t.server_config or {}, "disk_metrics": t.disk_metrics or {},
                                "checked_at": t.checked_at.isoformat() + "Z" if t.checked_at else None,
                                "compose_services": [{"name": m.name, "status": state if state in {"UNKNOWN", "DISABLED"} else m.status,
                                    "reason": m.reason, "containers": m.containers,
                                    "checked_at": m.checked_at.isoformat() + "Z" if m.checked_at else None} for m in members.get(t.id, [])]})
            health = []
            for h in session.scalars(select(Health)):
                threshold = settings.sheet_stale_after_seconds if h.name == "sheet" else (max(60, settings.alert_poll_seconds * 3) if h.name == "alert-worker" else (max(180, settings.rabbitmq_poll_seconds * 3) if h.name == "rabbitmq-worker" else settings.stale_after_seconds))
                state = "UNKNOWN"
                if h.last_ok_at:
                    state = "STALE" if stamp - h.last_ok_at > timedelta(seconds=threshold) else ("DEGRADED" if h.error else "UP")
                health.append({"component": h.name, "last_ok_at": h.last_ok_at.isoformat() + "Z" if h.last_ok_at else None,
                               "error": h.error, "status": state, "stale_after_seconds": threshold})
            incidents = [{"title": i.title, "detail": i.detail, "opened_at": i.opened_at.isoformat() + "Z"}
                         for i in session.scalars(select(Incident).where(Incident.active.is_(True)))]
            queue = session.scalar(select(func.count()).select_from(Outbox).where(Outbox.sent_at.is_(None)))
            queue_items = []
            for item in session.scalars(select(Outbox).where(Outbox.sent_at.is_(None)).order_by(Outbox.id).limit(5)):
                title = item.text.splitlines()[0] if item.text else "Thông báo"
                if item.incident_key.startswith("test:"):
                    try:
                        title = "🧪 " + str(json.loads(item.text).get("title", "Thử cảnh báo"))
                    except (ValueError, AttributeError):
                        title = "🧪 Thử cảnh báo"
                queue_items.append({"id": item.id, "title": title[:120], "attempts": item.attempts,
                                    "last_error": item.last_error[:350], "created_at": item.created_at.isoformat() + "Z",
                                    "next_attempt_at": item.next_attempt_at.isoformat() + "Z"})
            return {"targets": targets, "health": health, "incidents": incidents, "pending_notifications": queue, "notification_queue": queue_items,
                    "generated_at": stamp.isoformat() + "Z", "display_timezone": settings.display_timezone,
                    "stale_after_seconds": settings.stale_after_seconds,
                    "sheet_url": "https://docs.google.com/spreadsheets/d/" + quote(settings.google_sheet_id, safe="") + "/edit" if settings.google_sheet_id and not settings.google_sheet_id.startswith("YOUR_") else None}

    @app.get("/healthz")
    def healthz():
        try:
            with sessions() as session:
                session.execute(text("SELECT 1"))
        except Exception:
            raise HTTPException(503, "DB unavailable")
        return {"status": "ok"}

    @app.get("/api/status", dependencies=[Depends(authorize)])
    def status():
        if not settings.ready:
            raise HTTPException(409, "Cần cấu hình PostgreSQL trên giao diện")
        return snapshot()

    @app.get("/api/targets/{target_id}/availability", dependencies=[Depends(authorize)])
    def availability(target_id: int, period: str = "30d"):
        if period not in {"24h", "7d", "30d"}:
            raise HTTPException(422, "Khoảng thời gian phải là 24h, 7d hoặc 30d")
        from .availability import report
        with sessions() as session:
            if session.get(Target, target_id) is None:
                raise HTTPException(404, "Không tìm thấy đối tượng giám sát")
            return report(session, target_id, period, settings.stale_after_seconds)

    @app.post("/api/targets/archive", dependencies=[Depends(authorize)])
    def archive_targets(body: ArchiveRequest, request: Request):
        # Keep the action header in addition to the session/Origin CSRF checks.
        if request.headers.get("x-monitor-action") != "archive-disabled":
            raise HTTPException(403, "Yêu cầu phải được gửi từ dashboard")
        origin = request.headers.get("origin")
        if origin:
            try:
                allowed = urlsplit(origin).netloc.lower() == request.headers.get("host", "").lower()
            except ValueError:
                allowed = False
            if not allowed:
                raise HTTPException(403, "Nguồn yêu cầu không hợp lệ")
        ids = sorted(set(body.ids))
        if any(value <= 0 for value in ids):
            raise HTTPException(422, "ID đối tượng không hợp lệ")
        with sessions.begin() as session:
            targets = list(session.scalars(select(Target).where(Target.id.in_(ids))))
            if len(targets) != len(ids):
                raise HTTPException(409, "Danh sách đã thay đổi. Hãy làm mới và chọn lại")
            if any(target.enabled for target in targets):
                raise HTTPException(409, "Chỉ được xóa mục Đã tắt. Có mục đã bật lại; hãy làm mới danh sách")
            pending_ids = [target.id for target in targets if not target.archived]
            if pending_ids:
                changed = session.execute(update(Target).where(Target.id.in_(pending_ids), Target.enabled.is_(False), Target.archived.is_(False)).values(archived=True))
                if changed.rowcount != len(pending_ids):
                    raise HTTPException(409, "Trạng thái đã thay đổi trong lúc xóa. Không áp dụng; hãy thử lại")
        return {"ok": True, "archived_count": len(pending_ids)}

    @app.post("/api/notifications/test", dependencies=[Depends(authorize)])
    def test_notification(body: TestAlertRequest, request: Request):
        if request.headers.get("x-monitor-action") != "test-alert":
            raise HTTPException(403, "Yêu cầu phải được gửi từ dashboard")
        origin = request.headers.get("origin")
        if origin:
            try:
                allowed = urlsplit(origin).netloc.lower() == request.headers.get("host", "").lower()
            except ValueError:
                allowed = False
            if not allowed:
                raise HTTPException(403, "Nguồn yêu cầu không hợp lệ")
        if not settings.telegram_bot_token or not settings.telegram_chat_id:
            raise HTTPException(409, "Chưa cấu hình Telegram bot token và chat ID")
        title, message = body.title.strip(), body.message.strip()
        owners = list(dict.fromkeys(owner.strip() for owner in body.owners if owner.strip()))
        if not title or not message or any("\n" in owner or "\r" in owner or "," in owner or len(owner) > 200 for owner in owners):
            raise HTTPException(422, "Tiêu đề/nội dung không được trống; mỗi người phụ trách là một tên tối đa 200 ký tự")
        with sessions.begin() as session:
            item = Outbox(incident_key=f"test:{uuid4().hex}", text=json.dumps({"title": title, "message": message, "owners": owners}, ensure_ascii=False))
            session.add(item)
            session.flush()
            item_id = item.id
        return {"ok": True, "id": item_id, "status": "queued"}

    @app.get("/api/notifications/test/{notification_id}", dependencies=[Depends(authorize)])
    def test_notification_status(notification_id: int):
        with sessions() as session:
            item = session.get(Outbox, notification_id)
            if item is None or not item.incident_key.startswith("test:"):
                raise HTTPException(404, "Không tìm thấy tin thử nghiệm")
            previous = session.scalar(select(Outbox).where(Outbox.sent_at.is_(None), Outbox.id < item.id).order_by(Outbox.id).limit(1))
            ahead = session.scalar(select(func.count()).select_from(Outbox).where(Outbox.sent_at.is_(None), Outbox.id < item.id))
            worker = session.get(Health, "alert-worker")
            worker_ok = bool(worker and worker.last_ok_at and now() - worker.last_ok_at <= timedelta(seconds=max(60, settings.alert_poll_seconds * 3)))
            return {"id": item.id, "status": "sent" if item.sent_at else "queued", "attempts": item.attempts,
                    "last_error": item.last_error, "sent_at": item.sent_at.isoformat() + "Z" if item.sent_at else None,
                    "next_attempt_at": item.next_attempt_at.isoformat() + "Z", "queued_ahead": ahead,
                    "blocking_error": previous.last_error if previous else "", "worker_recent": worker_ok}

    @app.post("/api/notifications/retry", dependencies=[Depends(authorize)])
    def retry_notification(request: Request):
        if request.headers.get("x-monitor-action") != "retry-notification":
            raise HTTPException(403, "Yêu cầu phải được gửi từ dashboard")
        origin = request.headers.get("origin")
        if origin:
            try:
                allowed = urlsplit(origin).netloc.lower() == request.headers.get("host", "").lower()
            except ValueError:
                allowed = False
            if not allowed:
                raise HTTPException(403, "Nguồn yêu cầu không hợp lệ")
        if not settings.telegram_bot_token or not settings.telegram_chat_id:
            raise HTTPException(409, "Chưa cấu hình Telegram bot token và chat ID")
        with sessions.begin() as session:
            item = session.scalar(select(Outbox).where(Outbox.sent_at.is_(None)).order_by(Outbox.id).limit(1).with_for_update())
            if item is None:
                return {"ok": True, "id": None, "message": "Không còn tin đang chờ gửi"}
            if item.last_error == "Telegram rate limit" and item.next_attempt_at > now():
                raise HTTPException(409, "Telegram đang giới hạn tốc độ; cần chờ đến thời điểm thử lại")
            item.next_attempt_at = now()
            item_id = item.id
        return {"ok": True, "id": item_id, "message": f"Đã yêu cầu thử gửi lại tin #{item_id}. Worker sẽ xử lý trong chu kỳ tiếp theo (~{settings.alert_poll_seconds} giây nếu worker đang chạy)."}

    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request):
        if not control.authenticated(request.cookies.get(control.COOKIE)):
            return page()
        if not settings.ready:
            return RedirectResponse("/settings", status_code=303)
        return page()

    return app
