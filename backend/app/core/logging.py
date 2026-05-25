"""
app/core/logging.py
───────────────────
Structured logging using structlog.

- Development: colored, human-readable console output
- Production:  JSON lines (ready for Datadog / CloudWatch ingestion)

Usage:
    from app.core.logging import get_logger
    logger = get_logger(__name__)
    logger.info("document.indexed", doc_id=str(doc.id), chunks=42)
"""

import logging
import sys

import structlog
from structlog.types import EventDict, Processor

from app.core.config import settings


def _add_environment(
    logger: logging.Logger, method: str, event_dict: EventDict
) -> EventDict:
    """Inject environment and service name into every log entry."""
    event_dict["environment"] = settings.environment
    event_dict["service"] = "partsmind-backend"
    return event_dict


def setup_logging() -> None:
    """
    Call once at application startup (in app/main.py).
    Configures both structlog and stdlib logging so that
    third-party libraries (uvicorn, sqlalchemy) also go through
    the same pipeline.
    """
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        _add_environment,
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.is_production:
        # JSON output for log aggregation services
        renderer = structlog.processors.JSONRenderer()
    else:
        # Pretty colored output for local development
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(settings.log_level)
        ),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(settings.log_level)

    # Silence noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.BoundLogger:
    """
    Factory function — call at module level.

    Example:
        logger = get_logger(__name__)
        logger.info("search.completed", results=5, latency_ms=342)
    """
    return structlog.get_logger(name)
