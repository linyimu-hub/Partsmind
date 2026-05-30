"""
app/utils/metrics.py
──────────────────────
Lightweight metrics collection for AI-specific observability.

Tracks per-request:
  - Latency by stage (vision / search / synthesis)
  - Token usage + estimated cost
  - Cache hit rate
  - Confidence distribution

In production this feeds into:
  - A Grafana dashboard (via Prometheus or direct DB queries)
  - LangSmith project for AI-specific tracing
  - Admin analytics panel

For MVP we store in Redis with TTL, and query from Admin API.
"""

import time
from dataclasses import dataclass
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

# Token cost table ($/1M tokens, as of 2025)
TOKEN_COSTS = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "text-embedding-3-small": {"input": 0.02, "output": 0.0},
}


@dataclass
class RequestMetrics:
    """Metrics for a single agent request."""
    request_id: str
    session_id: str
    intent: str
    total_latency_ms: int

    # Stage breakdown
    vision_latency_ms: int = 0
    search_latency_ms: int = 0
    lookup_latency_ms: int = 0
    synthesis_latency_ms: int = 0

    # LLM usage
    prompt_tokens: int = 0
    completion_tokens: int = 0
    embedding_tokens: int = 0
    model: str = "gpt-4o"

    # Quality
    confidence: float = 0.0
    result_count: int = 0
    cache_hit: bool = False
    tools_used: list[str] = None

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens + self.embedding_tokens

    @property
    def estimated_cost_usd(self) -> float:
        costs = TOKEN_COSTS.get(self.model, TOKEN_COSTS["gpt-4o"])
        llm_cost = (
            self.prompt_tokens / 1_000_000 * costs["input"]
            + self.completion_tokens / 1_000_000 * costs["output"]
        )
        embed_costs = TOKEN_COSTS.get("text-embedding-3-small", {})
        embed_cost = self.embedding_tokens / 1_000_000 * embed_costs.get("input", 0.02)
        return round(llm_cost + embed_cost, 6)

    def log(self) -> None:
        """Emit structured log — picked up by log aggregation."""
        logger.info(
            "request.metrics",
            request_id=self.request_id,
            intent=self.intent,
            total_latency_ms=self.total_latency_ms,
            total_tokens=self.total_tokens,
            estimated_cost_usd=self.estimated_cost_usd,
            confidence=self.confidence,
            result_count=self.result_count,
            cache_hit=self.cache_hit,
        )


class LatencyTimer:
    """
    Context manager for timing code blocks.

    Usage:
        with LatencyTimer() as t:
            await some_slow_operation()
        latency_ms = t.elapsed_ms
    """
    def __init__(self) -> None:
        self._start: float = 0.0
        self.elapsed_ms: int = 0

    def __enter__(self) -> "LatencyTimer":
        self._start = time.monotonic()
        return self

    def __exit__(self, *args: Any) -> None:
        self.elapsed_ms = int((time.monotonic() - self._start) * 1000)


def estimate_tokens(text: str) -> int:
    """
    Rough token estimation without calling tiktoken.
    Rule of thumb: 1 token ≈ 4 chars for English, ≈ 2 chars for Chinese.
    Good enough for cost estimates; use tiktoken for exact counts.
    """
    # Detect if mostly Chinese (has CJK characters)
    cjk_count = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    if cjk_count > len(text) * 0.3:
        return len(text) // 2
    return len(text) // 4
