"""
Document parsers for different file formats.
"""

from __future__ import annotations

from fides.ingestion.parsers.base import BaseDocumentParser, ParsedDocument
from fides.ingestion.parsers.pdf import PDFParser
from fides.ingestion.parsers.text import TextParser

__all__ = ["BaseDocumentParser", "PDFParser", "ParsedDocument", "TextParser"]
