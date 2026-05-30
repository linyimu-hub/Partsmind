"""
Import all models here so that:
1. Alembic autogenerate can discover all tables
2. SQLAlchemy relationship resolution works correctly
"""
from app.models.chat import ChatMessage, ChatSession
from app.models.document import DocEmbedding, Document, DocumentChunk, DocumentStatus
from app.models.feedback import Feedback
from app.models.product import Product, ProductEmbedding
from app.models.user import User, UserRole

__all__ = [
    "User", "UserRole",
    "Product", "ProductEmbedding",
    "Document", "DocumentChunk", "DocEmbedding", "DocumentStatus",
    "ChatSession", "ChatMessage",
    "Feedback",
]
