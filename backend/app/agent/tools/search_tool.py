"""
app/agent/tools/search_tool.py
───────────────────────────────
SemanticSearchTool: pgvector cosine similarity search.

Two search modes:
1. semantic_search  — embed the query, find similar products by vector
2. keyword_search   — PostgreSQL full-text search (faster, less flexible)
3. hybrid_search    — run both, merge with Reciprocal Rank Fusion (RRF)

RRF formula: score = Σ 1 / (k + rank_i)  where k=60 (standard constant)
This is the same algorithm used by Elasticsearch hybrid search.
"""

import time
from typing import Any

from openai import AsyncOpenAI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_client = AsyncOpenAI(
    api_key=settings.openai_api_key,
    base_url=settings.openai_base_url or None,
)

async def embed_text(text_input: str) -> list[float]:
    """Convert text to embedding vector using OpenAI."""
    response = await _client.embeddings.create(
        model=settings.openai_embedding_model,
        input=text_input,
        encoding_format="float",
    )
    return response.data[0].embedding


async def semantic_search(
    db: AsyncSession,
    query: str,
    top_k: int = 10,
    category: str | None = None,
    brand: str | None = None,
    max_price: float | None = None,
) -> list[dict[str, Any]]:
    """
    Vector similarity search against product_embeddings.
    Returns products ranked by cosine similarity.
    """
    t_start = time.monotonic()
    query_embedding = await embed_text(query)

    # Build dynamic WHERE clause for filters
    filters = ["1=1"]
    
    embedding_literal = '[' + ','.join(str(x) for x in query_embedding) + ']'
    params: dict[str, Any] = {
        "embedding": embedding_literal,
        "top_k": top_k,
        "threshold": settings.rag_similarity_threshold,
    }

    if category:
        filters.append("p.category = :category")
        params["category"] = category
    if brand:
        filters.append("p.brand ILIKE :brand")
        params["brand"] = f"%{brand}%"
    if max_price:
        filters.append("p.price <= :max_price")
        params["max_price"] = max_price

    where_clause = " AND ".join(filters)

    # pgvector cosine similarity: 1 - (embedding <=> query_vector)
    sql = text(f"""
        SELECT
            p.id,
            p.part_number,
            p.name,
            p.description,
            p.category,
            p.brand,
            p.compatible_vehicles,
            p.specs,
            p.price,
            p.stock,
            p.image_url,
            1 - (pe.embedding <=> CAST(:embedding AS vector)) AS similarity_score
        FROM products p
        JOIN product_embeddings pe ON pe.product_id = p.id
            AND pe.embed_type = 'text'
       WHERE {where_clause}
            AND 1 - (pe.embedding <=> CAST(:embedding AS vector)) >= :threshold
        ORDER BY similarity_score DESC
        LIMIT :top_k
    """)

    result = await db.execute(sql, params)
    rows = result.mappings().all()

    latency_ms = int((time.monotonic() - t_start) * 1000)
    logger.info(
        "search_tool.semantic",
        query=query[:80],
        results=len(rows),
        latency_ms=latency_ms,
    )

    return [dict(row) for row in rows]


async def hybrid_search(
    db: AsyncSession,
    query: str,
    top_k: int = 10,
    **filters: Any,
) -> list[dict[str, Any]]:
    """
    Hybrid search using Reciprocal Rank Fusion (RRF).
    Combines semantic (vector) + keyword (full-text) results.
    Better recall than either alone.
    """
    t_start = time.monotonic()

    # Run both searches in parallel conceptually
    # (in production, use asyncio.gather for true parallelism)
    semantic_results = await semantic_search(db, query, top_k=top_k * 2, **filters)

    # Full-text search using PostgreSQL's tsvector
    fts_sql = text("""
        SELECT
            p.id,
            p.part_number,
            p.name,
            p.description,
            p.category,
            p.brand,
            p.compatible_vehicles,
            p.specs,
            p.price,
            p.stock,
            p.image_url,
            ts_rank(
                to_tsvector('english', p.name || ' ' || COALESCE(p.description, '') || ' ' || p.part_number),
                plainto_tsquery('english', :query)
            ) AS similarity_score
        FROM products p
        WHERE to_tsvector('english', p.name || ' ' || COALESCE(p.description, '') || ' ' || p.part_number)
              @@ plainto_tsquery('english', :query)
        ORDER BY similarity_score DESC
        LIMIT :top_k
    """)
    fts_result = await db.execute(fts_sql, {"query": query, "top_k": top_k * 2})
    keyword_results = [dict(row) for row in fts_result.mappings().all()]

    # ── Reciprocal Rank Fusion ────────────────────────────────
    k = 60  # RRF constant (standard value)
    rrf_scores: dict[str, float] = {}
    product_map: dict[str, dict] = {}

    for rank, product in enumerate(semantic_results):
        pid = str(product["id"])
        rrf_scores[pid] = rrf_scores.get(pid, 0) + 1 / (k + rank + 1)
        product_map[pid] = product

    for rank, product in enumerate(keyword_results):
        pid = str(product["id"])
        rrf_scores[pid] = rrf_scores.get(pid, 0) + 1 / (k + rank + 1)
        product_map.setdefault(pid, product)

    # Sort by combined RRF score
    sorted_ids = sorted(rrf_scores, key=lambda x: rrf_scores[x], reverse=True)

    merged = []
    for pid in sorted_ids[:top_k]:
        product = product_map[pid].copy()
        product["similarity_score"] = round(rrf_scores[pid], 4)
        product["match_type"] = "hybrid"
        merged.append(product)

    latency_ms = int((time.monotonic() - t_start) * 1000)
    logger.info(
        "search_tool.hybrid",
        query=query[:80],
        semantic_hits=len(semantic_results),
        keyword_hits=len(keyword_results),
        merged=len(merged),
        latency_ms=latency_ms,
    )

    return merged
