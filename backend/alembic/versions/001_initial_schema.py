"""Initial schema with pgvector extension

Revision ID: 001
Create Date: 2025-01-01
"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ── users ──────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="user"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # ── products ───────────────────────────────────────────
    op.create_table(
        "products",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("part_number", sa.String(100), nullable=False),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("brand", sa.String(100)),
        sa.Column("compatible_vehicles", JSONB, nullable=False, server_default="[]"),
        sa.Column("specs", JSONB, nullable=False, server_default="{}"),
        sa.Column("price", sa.Float),
        sa.Column("stock", sa.Integer, nullable=False, server_default="0"),
        sa.Column("image_url", sa.String(1000)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_products_part_number", "products", ["part_number"], unique=True)
    op.create_index("ix_products_category", "products", ["category"])
    op.create_index("ix_products_brand", "products", ["brand"])

    # ── product_embeddings ─────────────────────────────────
    op.create_table(
        "product_embeddings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("product_id", UUID(as_uuid=True),
                  sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column("embed_type", sa.String(20), nullable=False, server_default="text"),
    )
    op.create_index("ix_product_embeddings_product_id", "product_embeddings", ["product_id"])
    # HNSW index for fast ANN search
    op.execute("""
        CREATE INDEX ix_product_embeddings_hnsw
        ON product_embeddings
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)

    # ── documents ──────────────────────────────────────────
    op.create_table(
        "documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("file_type", sa.String(50), nullable=False),
        sa.Column("file_size_bytes", sa.Integer, nullable=False),
        sa.Column("storage_path", sa.String(1000), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text),
        sa.Column("chunk_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("doc_metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── document_chunks ────────────────────────────────────
    op.create_table(
        "document_chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", UUID(as_uuid=True),
                  sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("chunk_metadata", JSONB, nullable=False, server_default="{}"),
    )
    op.create_index("ix_doc_chunks_document_id", "document_chunks", ["document_id"])

    # ── doc_embeddings ─────────────────────────────────────
    op.create_table(
        "doc_embeddings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("chunk_id", UUID(as_uuid=True),
                  sa.ForeignKey("document_chunks.id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("embedding", Vector(1536), nullable=False),
    )
    op.execute("""
        CREATE INDEX ix_doc_embeddings_hnsw
        ON doc_embeddings
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)

    # ── chat_sessions ──────────────────────────────────────
    op.create_table(
        "chat_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(500), nullable=False, server_default="New conversation"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── chat_messages ──────────────────────────────────────
    op.create_table(
        "chat_messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", UUID(as_uuid=True),
                  sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("sources", JSONB),
        sa.Column("confidence", sa.Float),
        sa.Column("latency_ms", sa.Integer),
        sa.Column("tools_used", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── feedback ───────────────────────────────────────────
    op.create_table(
        "feedback",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("message_id", UUID(as_uuid=True), nullable=True),
        sa.Column("product_id", UUID(as_uuid=True),
                  sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True),
        sa.Column("rating", sa.String(10), nullable=False),
        sa.Column("comment", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("feedback")
    op.drop_table("chat_messages")
    op.drop_table("chat_sessions")
    op.drop_table("doc_embeddings")
    op.drop_table("document_chunks")
    op.drop_table("documents")
    op.drop_table("product_embeddings")
    op.drop_table("products")
    op.drop_table("users")
    op.execute("DROP EXTENSION IF EXISTS vector")
