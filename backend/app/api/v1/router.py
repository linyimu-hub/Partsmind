"""
app/api/v1/router.py
────────────────────
Central router — registers all endpoint modules.
Adding a new feature = add one line here.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import admin, auth, chat, documents, search

api_router = APIRouter()

api_router.include_router(auth.router,      prefix="/auth",      tags=["auth"])
api_router.include_router(search.router,    prefix="/search",    tags=["search"])
api_router.include_router(chat.router,      prefix="/chat",      tags=["chat"])
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(admin.router,     prefix="/admin",     tags=["admin"])
