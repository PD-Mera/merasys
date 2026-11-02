import ipaddress
import secrets

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from .collector import parse_inventory, record_result
from .db import Target


class DiskReport(BaseModel):
    path: str = Field(min_length=1, max_length=200)
    total_bytes: int | None = Field(default=None, ge=0, le=2 ** 63 - 1)
    free_bytes: int | None = Field(default=None, ge=0, le=2 ** 63 - 1)
    is_mount: bool = False
    error: str = Field(default="", max_length=80)


class Report(BaseModel):
    host: str = Field(max_length=45)
    docker_output: str | None = Field(default=None, max_length=4_000_000)
    services: dict[str, str] | None = Field(default=None, max_length=10000)
    disk_support: bool = False
    disks: list[DiskReport] | None = Field(default=None, max_length=16)


def router(settings, sessions):
    result = APIRouter()

    @result.post("/api/agent/report")
    def receive(report: Report, authorization: str = Header(default="")):
        try:
            ipaddress.ip_address(report.host)
        except ValueError:
            raise HTTPException(422, "Invalid host IP")
        try:
            tokens = settings.agent_tokens
        except Exception:
            raise HTTPException(503, "Agent authentication is not configured")
        expected = tokens.get(report.host)
        supplied = authorization.removeprefix("Bearer ") if authorization.startswith("Bearer ") else ""
        if not isinstance(expected, str) or len(expected) < 32 or not secrets.compare_digest(expected.encode(), supplied.encode()):
            raise HTTPException(401, "Invalid agent credentials")
        if not settings.ready:
            raise HTTPException(503, "Configure PostgreSQL in the web interface first")
        try:
            inventory = parse_inventory(report.docker_output) if report.docker_output is not None else None
        except (ValueError, TypeError):
            raise HTTPException(422, "Invalid Docker inventory")
        with sessions.begin() as session:
            parent = session.scalar(select(Target).where(Target.host == report.host, Target.container == "", Target.enabled.is_(True)))
            if parent is None:
                raise HTTPException(409, "Declare and enable this host in the Sheet first")
            record_result(session, report.host, inventory, "Agent không đọc được Docker; kiểm tra Docker daemon/quyền truy cập", max_gap_seconds=settings.stale_after_seconds, services=report.services, failure_threshold=settings.failure_threshold, recovery_threshold=settings.recovery_threshold)
            session.refresh(parent)
            from .disks import record
            record(parent, report.disks if report.disk_support else None, settings)
            paths = [item["path"] for item in (parent.server_config or {}).get("disks", [])] if parent.configured_enabled else []
        return {"ok": True, **({"disk_paths": paths} if report.disk_support else {})}

    return result
