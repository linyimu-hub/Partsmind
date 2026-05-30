"""
app/api/v1/endpoints/search.py
────────────────────────────────
POST /search/image   — upload image, get matching products
POST /search/text    — text query, get matching products
GET  /search/product/{id} — get single product details
"""

import base64
import uuid
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.lookup_tool import lookup_products
from app.agent.tools.search_tool import hybrid_search
from app.agent.tools.vision_tool import run_vision_tool
from app.api.deps.auth import get_current_user
from app.core.config import settings
from app.core.exceptions import UnsupportedFileTypeException
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.product import Product
from app.models.user import User
from app.schemas.product import ImageSearchRequest

logger = get_logger(__name__)
router = APIRouter()


@router.post("/image", response_model=dict)
async def image_search(
    file: UploadFile = File(...),
    vehicle_make: str | None = Form(None),
    vehicle_model: str | None = Form(None),
    vehicle_year: int | None = Form(None),
    top_k: int = Form(default=10),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """
    Upload an image of a part → AI identifies it → returns matching products.

    Flow:
      1. Validate image
      2. GPT-4o Vision identifies the part
      3. Use identified part name + attributes as search query
      4. Hybrid search → top-K products
      5. Return results with vision identification metadata
    """
    # Validate
    if file.content_type not in settings.allowed_image_types:
        raise UnsupportedFileTypeException(
            f"Image type '{file.content_type}' not supported. "
            f"Use: JPEG, PNG, or WebP"
        )

    file_bytes = await file.read()
    image_b64 = base64.b64encode(file_bytes).decode()

    # Vision identification
    logger.info("search.image_received", content_type=file.content_type, bytes=len(file_bytes))
    identified = await run_vision_tool(image_b64, file.content_type or "image/jpeg")

    # Build search query from vision output
    query_parts = [identified.get("part_name", "")]
    query_parts.extend(identified.get("search_terms", [])[:3])
    if identified.get("brand_visible"):
        query_parts.append(identified["brand_visible"])
    search_query = " ".join(filter(None, query_parts))

    # Search
    filters: dict[str, Any] = {}
    if vehicle_make:
        filters["vehicle_make"] = vehicle_make

    raw_results = await hybrid_search(
        db=db,
        query=search_query,
        top_k=top_k,
    )

    product_ids = [str(r["id"]) for r in raw_results[:top_k]]
    product_details = await lookup_products(db, product_ids)

    # Merge similarity scores into details
    score_map = {str(r["id"]): r["similarity_score"] for r in raw_results}
    for p in product_details:
        p["relevance_score"] = score_map.get(p["id"], 0.0)
        p["match_type"] = "visual+semantic"

    return {
        "identified_part": identified,
        "search_query": search_query,
        "results": product_details,
        "result_count": len(product_details),
    }


@router.post("/text", response_model=dict)
async def text_search(
    request: ImageSearchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Text-based hybrid search."""
    raw_results = await hybrid_search(
        db=db,
        query=request.query,
        top_k=request.top_k,
        category=request.category,
        brand=request.brand,
        max_price=request.max_price,
    )

    product_ids = [str(r["id"]) for r in raw_results]
    product_details = await lookup_products(db, product_ids)

    score_map = {str(r["id"]): r["similarity_score"] for r in raw_results}
    for p in product_details:
        p["relevance_score"] = score_map.get(p["id"], 0.0)
        p["match_type"] = "hybrid"

    return {
        "query": request.query,
        "results": product_details,
        "result_count": len(product_details),
    }


@router.get("/product/{product_id}")
async def get_product(
    product_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get single product by ID."""
    result = await db.execute(sa.select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        from app.core.exceptions import NotFoundException
        raise NotFoundException(f"Product {product_id} not found")

    details = await lookup_products(db, [str(product_id)])
    return details[0]
