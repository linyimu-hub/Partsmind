"""
Import all models here so that:
1. Alembic autogenerate can discover all tables
2. SQLAlchemy relationship resolution works correctly
"""
from app.models.user import User, UserRole
from app.models.product import Product, ProductEmbedding
from app.models.document import Document, DocumentChunk, DocEmbedding, DocumentStatus
from app.models.chat import ChatSession, ChatMessage
from app.models.feedback import Feedback

__all__ = [
    "User", "UserRole",
    "Product", "ProductEmbedding",
    "Document", "DocumentChunk", "DocEmbedding", "DocumentStatus",
    "ChatSession", "ChatMessage",
    "Feedback",
]
