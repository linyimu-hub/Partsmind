"""
app/schemas/product.py
──────────────────────
Product request/response schemas.
SearchResult wraps a product with a relevance score for ranking.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl


class VehicleCompatibility(BaseModel):
    make: str
    model: str
    year_from: int = Field(..., ge=1900, le=2100)
    year_to: int = Field(..., ge=1900, le=2100)
    engine: str | None = None


class ProductBase(BaseModel):
    part_number: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=500)
    description: str | None = None
    category: str = Field(..., max_length=100)
    brand: str | None = None
    compatible_vehicles: list[VehicleCompatibility] = []
    specs: dict[str, Any] = {}
    price: float | None = Field(None, ge=0)
    stock: int = Field(0, ge=0)


class ProductCreate(ProductBase):
    image_url: str | None = None


class ProductUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    price: float | None = Field(None, ge=0)
    stock: int | None = Field(None, ge=0)
    compatible_vehicles: list[VehicleCompatibility] | None = None
    specs: dict[str, Any] | None = None


class ProductResponse(ProductBase):
    id: UUID
    image_url: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class SearchResult(BaseModel):
    """A product result with relevance metadata."""
    product: ProductResponse
    relevance_score: float = Field(..., ge=0.0, le=1.0)
    match_type: str  # "visual" | "semantic" | "keyword" | "hybrid"
    matched_fields: list[str] = []  # e.g. ["name", "part_number", "compatible_vehicles"]


class ImageSearchRequest(BaseModel):
    """Used for text-only search; image search uses multipart/form-data."""
    query: str = Field(..., min_length=1, max_length=500)
    category: str | None = None
    brand: str | None = None
    max_price: float | None = None
    vehicle_make: str | None = None
    vehicle_model: str | None = None
    vehicle_year: int | None = None
    top_k: int = Field(10, ge=1, le=50)
