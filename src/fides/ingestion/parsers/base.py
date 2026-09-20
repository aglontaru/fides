"""
Abstract base class for document parsers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class ParsedDocument(BaseModel):
    """Represents a document after parsing, containing raw text and metadata."""

    title: str
    raw_text: str
    source_filename: str | None = None
    page_count: int | None = None
    metadata: dict[str, Any] = {}


class BaseDocumentParser(ABC):
    """Abstract base class for all document parsers."""

    @abstractmethod
    async def parse(self, content: bytes | str, filename: str | None = None) -> ParsedDocument:
        """
        Parse the content into a ParsedDocument.
        """
        ...

    @abstractmethod
    def supports(self, filename: str | None, content_type: str | None) -> bool:
        """
        Check if the parser supports the given file type.
        """
        ...
