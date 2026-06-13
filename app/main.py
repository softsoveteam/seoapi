import logging
import os

# Google OAuth may return expanded scopes; avoid oauthlib raising on scope mismatch.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.jobs.scheduler import start_scheduler, stop_scheduler
from app.routers import auth, dashboard, groups, keywords, reports, sites, sync

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    logger.info("SEOSOFT backend started")
    yield
    stop_scheduler()
    logger.info("SEOSOFT backend stopped")


app = FastAPI(title="SEOSOFT API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_url,
        "http://localhost:3000",
        "https://8.softsove.life",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(sites.router, prefix="/api/sites", tags=["sites"])
app.include_router(keywords.router, prefix="/api/keywords", tags=["keywords"])
app.include_router(groups.router, prefix="/api/groups", tags=["groups"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
app.include_router(sync.router, prefix="/api/sync", tags=["sync"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "seosoft-backend"}
