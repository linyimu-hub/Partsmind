"""
app/agent/tools/document_search_tool.py
─────────────────────────────────────────
RAG: 从文档库中检索相关 chunk。
和 search_tool.py（搜产品）的不同：
  - search_tool 返回产品（Product 表 + ProductEmbedding）
  - 这个工具返回文档 chunk（DocumentChunk 表 + DocEmbedding）
"""

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.services.embedding_service import embed_single

logger = get_logger(__name__)


async def search_documents(
    db: AsyncSession,
    query: str,
    top_k: int = 5,
    threshold: float = None,
) -> list[dict[str, Any]]:
    """
    在文档库中按语义相似度检索 top-K 个 chunk。
    返回:
        [
          {
            "chunk_id": "...",
            "document_id": "...",
            "document_name": "...",
            "content": "...",
            "chunk_index": 0,
            "similarity_score": 0.85,
            "metadata": {...}
          },
          ...
        ]
    """
    threshold = 0.2

    # 生成查询的 embedding
    query_embedding = await embed_single(query)
    embedding_literal = '[' + ','.join(str(x) for x in query_embedding) + ']'

    sql = text("""
        SELECT
            dc.id AS chunk_id,
            dc.document_id,
            d.original_filename AS document_name,
            dc.content,
            dc.chunk_index,
            dc.chunk_metadata,
            1 - (de.embedding <=> CAST(:embedding AS vector)) AS similarity_score
        FROM document_chunks dc
        JOIN doc_embeddings de ON de.chunk_id = dc.id
        JOIN documents d ON d.id = dc.document_id
        WHERE d.status = 'completed'
            AND 1 - (de.embedding <=> CAST(:embedding AS vector)) >= :threshold
        ORDER BY similarity_score DESC
        LIMIT :top_k
    """)

    result = await db.execute(sql, {
        "embedding": embedding_literal,
        "threshold": threshold,
        "top_k": top_k,
    })
    rows = result.fetchall()

    logger.info(
        "document_search.complete",
        query=query[:50],
        results=len(rows),
        threshold=threshold,
    )

    return [
        {
            "chunk_id": str(row.chunk_id),
            "document_id": str(row.document_id),
            "document_name": row.document_name,
            "content": row.content,
            "chunk_index": row.chunk_index,
            "metadata": row.chunk_metadata or {},
            "similarity_score": float(row.similarity_score),
        }
        for row in rows
    ]
