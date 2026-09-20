"""
PDF parser using PyMuPDF (fitz).
"""

from __future__ import annotations

import asyncio

import pymupdf as fitz
import structlog

from fides.ingestion.parsers.base import BaseDocumentParser, ParsedDocument

logger = structlog.get_logger(__name__)


class PDFParser(BaseDocumentParser):
    """Parser for PDF documents."""

    def __init__(self, batch_size: int = 20) -> None:
        """
        Initialize the PDF parser.

        Args:
            batch_size: Number of pages to process at once to avoid memory spikes.
        """
        self.batch_size = batch_size

    async def parse(self, content: bytes | str, filename: str | None = None) -> ParsedDocument:
        """
        Parse a PDF file. Handle large PDFs efficiently in batches.
        """
        if isinstance(content, str):
            raise ValueError("PDF parser expects bytes, got str")

        doc: fitz.Document | None = None
        text_parts: list[str] = []
        page_count = 0
        scanned_pages = 0

        try:
            # Yield control occasionally for large files
            await asyncio.sleep(0)
            doc = fitz.open(stream=content, filetype="pdf")
            page_count = len(doc)
            logger.info(f"Started parsing PDF with {page_count} pages", filename=filename)

            for i in range(0, page_count, self.batch_size):
                batch_end = min(i + self.batch_size, page_count)
                logger.debug(f"Processing pages {i} to {batch_end - 1}", filename=filename)

                for page_num in range(i, batch_end):
                    page = doc.load_page(page_num)
                    # Extract text with layout preservation
                    page_text = page.get_text("text")

                    if not page_text or len(page_text.strip()) < 50:
                        # Might be a scanned page
                        scanned_pages += 1

                    text_parts.append(page_text)

                # Yield control to event loop
                await asyncio.sleep(0)

            if scanned_pages > 0:
                logger.warning(
                    f"PDF may contain scanned pages ({scanned_pages}/{page_count} low-text pages)",
                    filename=filename,
                )

            full_text = "\n".join(text_parts)

            title = filename or "Unknown PDF Document"
            if doc.metadata and doc.metadata.get("title"):
                title = doc.metadata["title"]

            return ParsedDocument(
                title=title,
                raw_text=full_text,
                source_filename=filename,
                page_count=page_count,
                metadata={
                    "is_scanned": scanned_pages > (page_count * 0.5) if page_count else False,
                    "pdf_metadata": doc.metadata,
                },
            )

        except Exception as e:
            logger.error(f"Error parsing PDF: {e}", exc_info=True)
            raise e
        finally:
            if doc:
                doc.close()

    def supports(self, filename: str | None, content_type: str | None) -> bool:
        """Check if the parser supports this file type."""
        if content_type == "application/pdf":
            return True
        if filename and filename.lower().endswith(".pdf"):
            return True
        return False
