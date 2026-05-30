"""
app/core/monitoring.py
────────────────────────
Production monitoring setup.

Three layers:
1. Sentry     — unhandled exceptions, performance tracing
2. LangSmith  — AI-specific: every LLM call, tool use, latency, tokens
3. structlog  — structured JSON logs (shipped to Railway log drain)

Usage: called once at startup in app/main.py lifespan
"""

import os

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def setup_sentry() -> None:
    """Initialize Sentry error tracking."""
    if not settings.sentry_dsn:
        logger.info("monitoring.sentry_disabled", reason="no DSN configured")
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.celery import CeleryIntegration
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.environment,
            traces_sample_rate=0.1 if settings.is_production else 1.0,
            profiles_sample_rate=0.1,
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
                SqlalchemyIntegration(),
                CeleryIntegration(),
            ],
            # Don't send PII (user emails, IPs) to Sentry
            send_default_pii=False,
            before_send=_scrub_sensitive_data,
        )
        logger.info("monitoring.sentry_initialized", environment=settings.environment)
    except ImportError:
        logger.warning("monitoring.sentry_import_failed")


def _scrub_sensitive_data(event: dict, hint: dict) -> dict:
    """
    Remove sensitive data before sending to Sentry.
    Strips Authorization headers and request body passwords.
    """
    if "request" in event:
        headers = event["request"].get("headers", {})
        if "Authorization" in headers:
            headers["Authorization"] = "[REDACTED]"

        data = event["request"].get("data", {})
        if isinstance(data, dict) and "password" in data:
            data["password"] = "[REDACTED]"

    return event


def setup_langsmith() -> None:
    """
    Configure LangSmith tracing.
    When enabled, every LangChain/LangGraph call is automatically traced.
    No code changes needed — LangSmith hooks into LangChain internals.
    """
    if not settings.langchain_tracing_v2:
        logger.info("monitoring.langsmith_disabled")
        return

    if not settings.langchain_api_key:
        logger.warning("monitoring.langsmith_no_key")
        return

    # LangSmith reads these env vars automatically
    os.environ["LANGCHAIN_TRACING_V2"]  = "true"
    os.environ["LANGCHAIN_API_KEY"]     = settings.langchain_api_key
    os.environ["LANGCHAIN_PROJECT"]     = settings.langchain_project
    os.environ["LANGCHAIN_ENDPOINT"]    = settings.langchain_endpoint

    logger.info(
        "monitoring.langsmith_enabled",
        project=settings.langchain_project,
    )


def setup_monitoring() -> None:
    """Call once at application startup."""
    setup_sentry()
    setup_langsmith()
    logger.info(
        "monitoring.initialized",
        environment=settings.environment,
        sentry=bool(settings.sentry_dsn),
        langsmith=settings.langchain_tracing_v2,
    )
