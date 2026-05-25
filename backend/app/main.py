"""
app/main.py — FastAPI application factory (production version)
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.core.exceptions import register_exception_handlers
from app.core.monitoring import setup_monitoring
from app.db.session import init_db

setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("app.startup", environment=settings.environment, version="0.1.0")
    setup_monitoring()
    await init_db()
    logger.info("app.ready")
    yield
    logger.info("app.shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="PartsMind API",
        description="AI-powered auto parts search and Q&A — 源尧兴实业",
        version="0.1.0",
        docs_url="/docs" if settings.is_development else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.is_development else None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    register_exception_handlers(app)

    from app.api.v1.router import api_router
    app.include_router(api_router, prefix=settings.api_prefix)

    @app.get("/health", tags=["ops"])
    async def health():
        return {
            "status": "ok",
            "environment": settings.environment,
            "version": "0.1.0",
        }

    return app


app = create_app()
