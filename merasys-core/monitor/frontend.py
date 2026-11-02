"""Serve the Vite build from the mounted frontend directory on every request."""
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"


def page():
    try:
        html = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
    except FileNotFoundError:
        raise HTTPException(503, "Chưa có frontend build. Build frontend theo FRONTEND.md trước khi mở web.") from None
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


def attach_assets(app):
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets", check_dir=False), name="frontend-assets")
