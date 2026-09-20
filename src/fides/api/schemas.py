"""
Pydantic schemas for the Fides API.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class SourceReference(BaseModel):
    document: str
    article: str | None = None
    paragraph: str | None = None
    text_excerpt: str


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    sources: list[SourceReference] | None = None
    timestamp: datetime


class DocumentUploadResponse(BaseModel):
    status: Literal["new", "identical", "updated"]
    document_title: str
    details: str
    articles_indexed: int | None = None


class SystemStatus(BaseModel):
    status: Literal["healthy", "degraded", "error"]
    neo4j_connected: bool
    mcp_server_connected: bool
    llm_provider: str
    indexed_documents: int
