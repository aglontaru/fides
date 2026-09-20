"""
Plain text parser.
"""

from __future__ import annotations

import asyncio

from fides.ingestion.parsers.base import BaseDocumentParser, ParsedDocument


class TextParser(BaseDocumentParser):
    """Parser for raw text input."""

    async def parse(self, content: bytes | str, filename: str | None = None) -> ParsedDocument:
        """
        Parse plain text content.
        """
        await asyncio.sleep(0)

        text_content = ""
        if isinstance(content, bytes):
            text_content = content.decode("utf-8", errors="replace")
        else:
            text_content = content

        title = filename or "Text Input"

        return ParsedDocument(
            title=title, raw_text=text_content, source_filename=filename, page_count=1, metadata={}
        )

    def supports(self, filename: str | None, content_type: str | None) -> bool:
        """Check if parser supports the given input."""
        if content_type and content_type.startswith("text/"):
            return True
        if filename and filename.lower().endswith((".txt", ".md", ".csv")):
            return True
        # Text parser is generally a fallback for string input
        return True
