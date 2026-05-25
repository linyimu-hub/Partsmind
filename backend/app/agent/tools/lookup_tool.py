"""
app/agent/tools/lookup_tool.py
───────────────────────────────
ProductLookupTool: Fetch full product details by IDs.
CompatibilityTool: Check if a part fits a specific vehicle.

Why separate from search_tool?
Search returns candidates (partial data, ranked by similarity).
Lookup fetches complete structured data for specific products.
This two-step pattern avoids pulling all JSONB fields during search
(better DB performance).
"""

import time
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.product import Product

logger = get_logger(__name__)


async def lookup_products(
    db: AsyncSession,
    product_ids: list[str],
) -> list[dict[str, Any]]:
    """
    Fetch full product details for a list of IDs.
    Preserves ordering to match search ranking.
    """
    if not product_ids:
        return []

    t_start = time.monotonic()

    uuids = [UUID(pid) for pid in product_ids]
    result = await db.execute(
        select(Product).where(Product.id.in_(uuids))
    )
    products = result.scalars().all()

    # Restore original ordering (DB doesn't guarantee IN clause order)
    product_map = {str(p.id): p for p in products}
    ordered = [product_map[pid] for pid in product_ids if pid in product_map]

    details = []
    for p in ordered:
        details.append({
            "id": str(p.id),
            "part_number": p.part_number,
            "name": p.name,
            "description": p.description,
            "category": p.category,
            "brand": p.brand,
            "compatible_vehicles": p.compatible_vehicles,
            "specs": p.specs,
            "price": p.price,
            "stock": p.stock,
            "image_url": p.image_url,
            "in_stock": p.stock > 0,
        })

    logger.info(
        "lookup_tool.products",
        requested=len(product_ids),
        found=len(details),
        latency_ms=int((time.monotonic() - t_start) * 1000),
    )
    return details


def check_vehicle_compatibility(
    product: dict[str, Any],
    vehicle_make: str | None,
    vehicle_model: str | None,
    vehicle_year: int | None,
) -> dict[str, Any]:
    """
    Check if a product is compatible with the given vehicle.
    Returns compatibility result with explanation.

    compatible_vehicles format:
    [{"make": "Toyota", "model": "Camry", "year_from": 2018, "year_to": 2023}]
    """
    if not any([vehicle_make, vehicle_model, vehicle_year]):
        return {"compatible": None, "reason": "No vehicle specified"}

    compatible_vehicles: list[dict] = product.get("compatible_vehicles", [])

    if not compatible_vehicles:
        return {
            "compatible": None,
            "reason": "Compatibility data not available for this part",
        }

    for compat in compatible_vehicles:
        make_match = (
            not vehicle_make
            or compat.get("make", "").lower() == vehicle_make.lower()
        )
        model_match = (
            not vehicle_model
            or compat.get("model", "").lower() == vehicle_model.lower()
        )
        year_match = (
            not vehicle_year
            or (
                compat.get("year_from", 0) <= vehicle_year <= compat.get("year_to", 9999)
            )
        )

        if make_match and model_match and year_match:
            return {
                "compatible": True,
                "reason": (
                    f"Confirmed compatible with {compat['make']} {compat['model']} "
                    f"({compat['year_from']}–{compat['year_to']})"
                ),
                "matched_spec": compat,
            }

    # Found vehicles but none matched
    makes_supported = list({v["make"] for v in compatible_vehicles})
    return {
        "compatible": False,
        "reason": (
            f"This part is not listed for "
            f"{vehicle_year or ''} {vehicle_make or ''} {vehicle_model or ''}. "
            f"Supported makes: {', '.join(makes_supported)}"
        ),
        "supported_vehicles": compatible_vehicles,
    }
