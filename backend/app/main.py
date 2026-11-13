from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging

configure_logging()
app = FastAPI(title="Presidio Support Chatbot API")
register_error_handlers(app)
app.include_router(auth_router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Presidio Support Chatbot API"}
