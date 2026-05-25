"""
使用 OpenAI 官方 API embedding
text-embedding-3-small (1536 维)
"""

import asyncio
import time
from typing import Any

from openai import AsyncOpenAI, RateLimitError

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# 加大 timeout 应对国内网络慢
_client = AsyncOpenAI(
    api_key=settings.openai_api_key,
    base_url=settings.openai_base_url or None,
    timeout=120.0,   # 2分钟超时
    max_retries=3,
)

EMBED_BATCH_SIZE = 25 # 批次小一点避免单次请求过大


async def embed_texts(
    texts: list[str],
    redis_client: Any = None,
) -> list[list[float]]:
    t_start = time.monotonic()
    results: list[list[float]] = []
    total_tokens = 0

    for batch_start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[batch_start: batch_start + EMBED_BATCH_SIZE]
        logger.info(f"embedding batch {batch_start // EMBED_BATCH_SIZE + 1}, size={len(batch)}")

        for attempt in range(3):
            try:
                response = await _client.embeddings.create(
                    model=settings.openai_embedding_model,
                    input=batch,
                    encoding_format="float",
                )
                break
            except RateLimitError:
                wait = 2 ** attempt
                await asyncio.sleep(wait)
            except Exception as e:
                print(f"Embedding error: {type(e).__name__}: {e}")
                raise
        else:
            raise RuntimeError("Embedding API failed after retries")
        total_tokens += response.usage.total_tokens
        results.extend([item.embedding for item in response.data])

    latency_ms = int((time.monotonic() - t_start) * 1000)
    logger.info("embedding.complete", count=len(texts), tokens=total_tokens, latency_ms=latency_ms)
    return results


async def embed_single(text: str) -> list[float]:
    results = await embed_texts([text])
    return results[0]
