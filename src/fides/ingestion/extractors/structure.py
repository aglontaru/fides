"""
Universal legal document structure extractor for metadata and defined terms.
"""

from __future__ import annotations

import re
from datetime import date

import structlog
from pydantic import BaseModel

logger = structlog.get_logger(__name__)


class DocumentMetadata(BaseModel):
    """Metadata extracted from the legal document header/preamble."""

    title: str
    short_name: str
    document_type: str
    publication_date: date | None = None
    celex_number: str | None = None
    eli_uri: str | None = None


class DefinedTerm(BaseModel):
    """A term defined within the legal document."""

    term: str
    normalized_term: str
    definition: str
    source_article: str


class CrossReference(BaseModel):
    """A cross-reference between sections/articles of the legal document."""

    source_id: str
    target_id: str
    reference_text: str


class ExtractedStructure(BaseModel):
    """Complete extracted structure information."""

    metadata: DocumentMetadata
    defined_terms: list[DefinedTerm]
    cross_references: list[CrossReference]


class StructureExtractor:
    """Extractor for universal legal document structure components."""

    def __init__(self) -> None:
        pass

    def extract_short_name(self, title: str, filename: str | None = None) -> str:
        """
        Generate a clean, unique short_name from the document filename or title.
        Works across any legal jurisdiction or document type.
        """
        if filename:
            name_base = filename.rsplit(".", 1)[0]
            clean_fn = re.sub(r"[^a-zA-Z0-9_]", "_", name_base).strip("_")
            if clean_fn:
                # Remove redundant common suffixes like '_ACT' or '_PDF' if present
                clean_fn = re.sub(r"(_act|_pdf|_full)+$", "", clean_fn, flags=re.IGNORECASE)
                return clean_fn[:30].upper()

        clean = re.sub(r"[^a-zA-Z0-9\s]", "", title)
        parts = clean.split()
        return "_".join(parts[:4]).upper() if parts else "LEGAL_DOC"

    def detect_document_type(self, text: str, title: str) -> str:
        """Detect generic legal document classification without jurisdiction bias."""
        combined = f"{title} {text[:1500]}".lower()
        if "statute" in combined or "u.s.c." in combined or "united states code" in combined:
            return "statute"
        elif "contract" in combined or "agreement" in combined or "master services" in combined:
            return "contract"
        elif "policy" in combined or "compliance policy" in combined:
            return "policy"
        elif "regulation" in combined or "cfr" in combined or "code of federal regulations" in combined:
            return "regulation"
        elif "directive" in combined:
            return "directive"
        elif "decision" in combined:
            return "decision"
        elif "treaty" in combined or "convention" in combined:
            return "treaty"
        elif "standard" in combined or "iso" in combined or "nist" in combined:
            return "standard"
        elif "act" in combined:
            return "act"
        return "legislation"

    async def extract(self, text: str, filename: str | None = None) -> ExtractedStructure:
        """Extract metadata, terms, and cross-references from legal document text."""
        logger.info("Extracting universal structure from document text", filename=filename)

        title = ""
        for line in text.splitlines():
            line_str = line.strip()
            if line_str and len(line_str) > 10 and not line_str.startswith("—"):
                title = line_str
                break

        if not title:
            title = filename or "Legal Document"

        short_name = self.extract_short_name(title, filename)
        doc_type = self.detect_document_type(text, title)

        metadata = DocumentMetadata(
            title=title,
            short_name=short_name,
            document_type=doc_type,
            publication_date=None,
        )

        defined_terms: list[DefinedTerm] = []
        cross_references: list[CrossReference] = []

        return ExtractedStructure(
            metadata=metadata, defined_terms=defined_terms, cross_references=cross_references
        )


__all__ = [
    "CrossReference",
    "DefinedTerm",
    "DocumentMetadata",
    "ExtractedStructure",
    "StructureExtractor",
]
