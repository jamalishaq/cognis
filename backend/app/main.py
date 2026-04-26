from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.api import analyse, chat, health, incidents, resolve

app = FastAPI(title="Cognis", version="0.1.0")

_ALLOWED_ORIGINS = {
    "local": ["http://localhost:5173", "http://localhost:3000"],
    "dev": ["https://dev.cognis.internal"],
    "prod": ["https://cognis.internal"],
}

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS.get(settings.environment, []),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(analyse.router)
app.include_router(chat.router)
app.include_router(incidents.router)
app.include_router(resolve.router)
