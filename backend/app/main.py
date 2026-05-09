# patch_all() must run before any boto3 client is created.
# config.py creates an SSM client at module level in non-local environments,
# so these two lines must stay above all other imports.
from aws_xray_sdk.core import patch_all, xray_recorder

patch_all()
xray_recorder.configure(service="cognis", context_missing="LOG_ERROR")

import uuid

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from structlog.contextvars import bind_contextvars, clear_contextvars

from app.config import settings
from app.logger import setup_logging
from app.api import analyse, chat, health, incidents, resolve

setup_logging()

log = structlog.get_logger()

app = FastAPI(title="Cognis", version="0.1.0")

_ALLOWED_ORIGINS = {
    "local": ["http://localhost:5173", "http://localhost:3000"],
    "dev": [settings.frontend_origin] if settings.frontend_origin else [],
    "prod": [settings.frontend_origin] if settings.frontend_origin else [],
}

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS.get(settings.environment, []),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    clear_contextvars()

    trace_id = None
    try:
        segment = xray_recorder.current_segment()
        trace_id = segment.trace_id if segment else None
    except Exception:
        pass

    bind_contextvars(
        request_id=str(uuid.uuid4()),
        endpoint=request.url.path,
        method=request.method,
        trace_id=trace_id,
    )

    return await call_next(request)

app.include_router(health.router)
app.include_router(analyse.router)
app.include_router(chat.router)
app.include_router(incidents.router)
app.include_router(resolve.router)
