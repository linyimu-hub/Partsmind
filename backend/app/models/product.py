"""
app/models/product.py
─────────────────────
Product (auto part) model.

Design notes:
- compatible_vehicles stored as JSONB: [{"make":"Toyota","model":"Camry","year_from":2018,"year_to":2023}]
  Flexible schema allows varied compatibility data without extra tables.
- specs stored as JSONB: {"weight_kg": 1.2, "material": "steel", "oem_number": "04465-02220"}
  Different part categories have completely different specs, JSONB handles this cleanly.
- embedding stored separately in ProductEmbedding (one product → multiple embed types:
  text-based for Q&A, image-based for visual search)
"""

import uuid
from typing import TYPE_CHECKING, Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.feedback import Feedback


class Product(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "products"

    part_number: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    brand: Mapped[str | None] = mapped_column(String(100), index=True)

    # JSONB fields — flexible structured data
    compatible_vehicles: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    specs: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    # Commerce fields
    price: Mapped[float | None] = mapped_column(Float)
    stock: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(1000))

    # Relationships
    embeddings: Mapped[list["ProductEmbedding"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    feedbacks: Mapped[list["Feedback"]] = relationship(back_populates="product")

    def __repr__(self) -> str:
        return f"<Product {self.part_number}: {self.name}>"


class ProductEmbedding(Base):
    """
    Separate embedding table — one product can have multiple embedding types.
    embed_type: "text" (for RAG Q&A) | "image" (for visual similarity search)
    """
    __tablename__ = "product_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # text-embedding-3-small → 1536 dims
    embedding: Mapped[list[float]] = mapped_column(Vector(1536), nullable=False)
    embed_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="text"  # "text" | "image"
    )

    product: Mapped["Product"] = relationship(back_populates="embeddings")
