import ipaddress
import re
import secrets
import sqlite3
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from . import control, configuration
from .frontend import page


class Login(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class ConfigPatch(BaseModel):
    values: dict = Field(default_factory=dict, max_length=40)
    clear: list[str] = Field(default_factory=list, max_length=4)


class AgentHost(BaseModel):
    host: str = Field(max_length=45)
    replace: bool = False
    previous_host: str | None = Field(default=None, max_length=45)


class AgentTokenValue(BaseModel):
    previous_host: str | None = Field(default=None, max_length=45)
    token: str = Field(min_length=32, max_length=256, pattern=r"^[A-Za-z0-9_-]+$")
    replace: bool = False


class PasswordChange(BaseModel):
    current: str = Field(min_length=1, max_length=256)
    new: str = Field(min_length=1, max_length=256)


def csrf(request):
    if request.headers.get("x-merasys-request") != "1":
        raise HTTPException(403, "Yêu cầu phải được gửi từ giao diện Merasys")
    origin = request.headers.get("origin")
    if origin:
        try:
            parts = urlsplit(origin)
            valid = parts.scheme == request.url.scheme and parts.netloc.lower() == request.headers.get("host", "").lower()
        except ValueError:
            valid = False
        if not valid:
            raise HTTPException(403, "Nguồn yêu cầu không hợp lệ")


def authorize(request: Request):
    if not control.authenticated(request.cookies.get(control.COOKIE)):
        raise HTTPException(401, "Phiên đăng nhập đã hết hạn")
    if request.method not in {"GET", "HEAD"}:
        csrf(request)


def session_response(request):
    response = JSONResponse({"ok": True})
    response.set_cookie(control.COOKIE, control.new_session(), max_age=control.SESSION_SECONDS,
                        httponly=True, secure=request.url.scheme == "https", samesite="strict", path="/")
    return response


def attach(app, settings):
    @app.middleware("http")
    async def headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/auth/state")
    def auth_state(request: Request):
        return {"registered": control.registered(), "authenticated": control.authenticated(request.cookies.get(control.COOKIE))}

    @app.post("/api/auth/register")
    def register(body: Login, request: Request):
        csrf(request)
        if control.registered():
            raise HTTPException(409, "Đã có tài khoản; hệ thống chỉ cho phép một tài khoản")
        address = request.client.host if request.client else "unknown"
        if not control.allow_login_attempt(address):
            raise HTTPException(429, "Thử quá nhiều lần; vui lòng chờ 15 phút")
        if not re.fullmatch(r"[A-Za-z0-9_.@-]{3,64}", body.username):
            raise HTTPException(422, "Tên đăng nhập dùng chữ/số/_.@-")
        try:
            control.register(body.username, body.password)
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Đã có tài khoản; hãy đăng nhập") from None
        control.login_result(address, True)
        return session_response(request)

    @app.post("/api/auth/login")
    def login(body: Login, request: Request):
        csrf(request)
        address = request.client.host if request.client else "unknown"
        if not control.allow_login_attempt(address):
            raise HTTPException(429, "Đăng nhập sai quá nhiều lần; vui lòng chờ 15 phút")
        valid = control.check_login(body.username, body.password)
        control.login_result(address, valid)
        if not valid:
            raise HTTPException(401, "Tên đăng nhập hoặc mật khẩu không đúng")
        return session_response(request)

    @app.post("/api/auth/logout", dependencies=[Depends(authorize)])
    def logout(request: Request):
        control.logout(request.cookies.get(control.COOKIE, ""))
        response = JSONResponse({"ok": True})
        response.delete_cookie(control.COOKIE, path="/")
        return response

    @app.post("/api/auth/password", dependencies=[Depends(authorize)])
    def change_password(body: PasswordChange):
        if not control.change_password(body.current, body.new):
            raise HTTPException(400, "Mật khẩu hiện tại không đúng")
        response = JSONResponse({"ok": True})
        response.delete_cookie(control.COOKIE, path="/")
        return response

    @app.get("/settings")
    def settings_page(request: Request):
        if not control.authenticated(request.cookies.get(control.COOKIE)):
            return RedirectResponse("/", status_code=303)
        return page()

    @app.get("/api/settings", dependencies=[Depends(authorize)])
    def get_settings():
        return configuration.public(settings)

    @app.put("/api/settings", dependencies=[Depends(authorize)])
    def save_settings(body: ConfigPatch):
        try:
            configuration.save(settings, body.values, body.clear)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        except Exception:
            raise HTTPException(400, "Không kết nối/khởi tạo được PostgreSQL; kiểm tra URL, mật khẩu, mạng và quyền DB") from None
        return {"ok": True, **configuration.public(settings)}

    @app.post("/api/settings/agent-token", dependencies=[Depends(authorize)])
    def agent_token(body: AgentHost):
        try:
            ipaddress.ip_address(body.host)
            if body.previous_host is not None:
                ipaddress.ip_address(body.previous_host)
        except ValueError:
            raise HTTPException(422, "IP không hợp lệ") from None
        token = secrets.token_urlsafe(32)
        try:
            control.assign_agent_token(body.host, token, body.replace, body.previous_host)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        settings.reload()
        return {"host": body.host, "token": token}

    @app.put("/api/settings/agent-token/{host}", dependencies=[Depends(authorize)])
    def save_agent_token(host: str, body: AgentTokenValue):
        try:
            ipaddress.ip_address(host)
            if body.previous_host is not None:
                ipaddress.ip_address(body.previous_host)
        except ValueError:
            raise HTTPException(422, "IP không hợp lệ") from None
        try:
            control.assign_agent_token(host, body.token, body.replace, body.previous_host)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        settings.reload()
        return {"ok": True}

    @app.delete("/api/settings/agent-token/{host}", dependencies=[Depends(authorize)])
    def delete_agent_token(host: str):
        try:
            ipaddress.ip_address(host)
        except ValueError:
            raise HTTPException(422, "IP không hợp lệ") from None
        control.remove_agent_token(host)
        settings.reload()
        return {"ok": True}

    @app.post("/api/settings/sync", dependencies=[Depends(authorize)])
    def sync_now():
        if not settings.sheet_ready:
            raise HTTPException(409, "Cần cấu hình PostgreSQL và Google Sheet trước")
        try:
            from .settings import LiveSessions
            from .sheet import sync_sheet
            sync_sheet(settings, LiveSessions(settings))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        except Exception:
            raise HTTPException(400, "Không đồng bộ được Sheet; kiểm tra key, quyền chia sẻ, tab và mạng") from None
        return {"ok": True}
