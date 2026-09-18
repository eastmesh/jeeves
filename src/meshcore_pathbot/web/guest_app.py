"""FastAPI application factory for the read-only guest web GUI."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..config.schema import AppConfig
from ..core.bot import PathBot
from ..core.message_store import MessageStore
from ..core.repeater_db import ADV_TYPE_NAMES, RepeaterDB
from ..events.bus import EventBus

WEB_DIR = Path(__file__).parent
TEMPLATES_DIR = WEB_DIR / "templates" / "guest"
STATIC_DIR = WEB_DIR / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


def create_guest_app(
    config: AppConfig,
    bot: PathBot,
    db: RepeaterDB,
    bus: EventBus,
    message_store: MessageStore,
) -> FastAPI:
    """Create the read-only guest FastAPI application.

    Only exposes paths, overlaps, and repeaters (without delete).
    """
    app = FastAPI(
        title="MeshCore Jeeves2.0",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.state.config = config
    app.state.bot = bot
    app.state.db = db
    app.state.bus = bus
    app.state.message_store = message_store

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    # Same custom Jinja2 filters as the main app
    def format_timestamp(ts: float | int | None) -> str:
        if not ts:
            return "--"
        try:
            dt = datetime.fromtimestamp(float(ts))
            return dt.strftime("%H:%M:%S")
        except (ValueError, OSError):
            return "--"

    def format_relative(ts: float | int | None) -> str:
        if not ts:
            return "--"
        try:
            dt = datetime.fromtimestamp(float(ts))
            return dt.strftime("%d/%m/%y %H:%M:%S")
        except (ValueError, OSError):
            return "--"

    def format_datetime(ts: float | int | None) -> str:
        if not ts:
            return ""
        try:
            dt = datetime.fromtimestamp(float(ts))
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, OSError):
            return ""

    templates.env.filters["fmt_time"] = format_timestamp
    templates.env.filters["fmt_relative"] = format_relative
    templates.env.filters["fmt_datetime"] = format_datetime
    templates.env.filters["adv_type_name"] = lambda t: ADV_TYPE_NAMES.get(int(t or 0), f"type{t}")
    app.state.templates = templates

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


    @app.middleware("http")
    async def track_guest_page_visits(request, call_next):
        response = await call_next(request)

        if request.method == "GET" and request.url.path in {"/", "/paths"}:
            forwarded_for = request.headers.get("x-forwarded-for", "")
            if forwarded_for:
                ip_address = forwarded_for.split(",", 1)[0].strip()
            else:
                ip_address = request.client.host if request.client else "unknown"
            await db.record_guest_visit(ip_address=ip_address, path=request.url.path)

        return response

    from .routes import guest_api, guest_dashboard, guest_paths

    app.include_router(guest_dashboard.router)
    app.include_router(guest_paths.router)
    app.include_router(guest_api.router, prefix="/api")

    return app
