from contextlib import asynccontextmanager
import logging
from uuid import uuid4

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from app.api.admin_documents import router as admin_documents_router
from app.api.chat import router as chat_router
from app.api.conversations import router as conversations_router
from app.api.auth import router as auth_router
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.config import get_settings
from app.services.staleness import expire_stale_documents

configure_logging()


class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        limit = get_settings().max_request_size_bytes
        content_length = request.headers.get("content-length")
        try:
            oversized = bool(content_length and int(content_length) > limit)
        except ValueError:
            oversized = True
        if oversized:
            response = JSONResponse(
                {"error": {"code": "request_too_large", "message": "Request is too large"}},
                status_code=413,
            )
        else:
            request.state.request_id = request_id
            response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'none'"
        logging.getLogger("app.request").info(
            "request_completed",
            extra={"request_id": request_id, "method": request.method, "path": request.url.path, "status": response.status_code},
        )
        return response


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
app.add_middleware(SecurityMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in get_settings().cors_allowed_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)
register_error_handlers(app)
app.include_router(auth_router)
app.include_router(admin_documents_router)
app.include_router(chat_router)
app.include_router(conversations_router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Presidio Support Chatbot API"}
