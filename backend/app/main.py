from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI

from app.api.admin_documents import router as admin_documents_router
from app.api.auth import router as auth_router
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.config import get_settings
from app.services.staleness import expire_stale_documents

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        expire_stale_documents,
        "interval",
        seconds=get_settings().staleness_job_interval_seconds,
        id="expire-stale-documents",
        replace_existing=True,
    )
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="Presidio Support Chatbot API", lifespan=lifespan)
register_error_handlers(app)
app.include_router(auth_router)
app.include_router(admin_documents_router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Presidio Support Chatbot API"}
