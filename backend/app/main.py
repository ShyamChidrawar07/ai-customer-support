
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import get_settings
from app.core.exceptions import NotFoundError, register_exception_handlers
from app.db.session import get_engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.settings = settings
    get_engine()
    print(f"Starting {settings.APP_NAME} ({settings.APP_ENV})")
    yield
    
    get_engine().dispose()
    print("Application shutdown complete")

def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.APP_NAME,lifespan=lifespan)
    app.include_router(api_router)
    register_exception_handlers(app)
    return app

app = create_app()

@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}

@app.get("/test-error")
async def test_error():
    raise NotFoundError("Ticket not found.")