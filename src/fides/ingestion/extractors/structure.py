"""
Legislation structure extractor for metadata and defined terms.
"""

from __future__ import annotations

import re
from datetime import date

import structlog
from pydantic import BaseModel

logger = structlog.get_logger(__name__)


class DocumentMetadata(BaseModel):
    """Metadata extracted from the legislation preamble."""

    title: str
    short_name: str
    document_type: str
    publication_date: date | None = None
    celex_number: str | None = None
    eli_uri: str | None = None


class DefinedTerm(BaseModel):
    """A term defined within the legislation."""

    term: str
    normalized_term: str
    definition: str
    source_article: str


class CrossReference(BaseModel):
    """A cross-reference between sections/articles of legislation."""

    source_id: str
    target_id: str
    reference_text: str


class ExtractedStructure(BaseModel):
    """Complete extracted structure information."""

    metadata: DocumentMetadata
    defined_terms: list[DefinedTerm]
    cross_references: list[CrossReference]


class StructureExtractor:
    """Extractor for legislation structure components."""

    def __init__(self) -> None:
        pass

    def extract_short_name(self, title: str, filename: str | None = None) -> str:
        """
        Generate a short_name from the document title or filename.
        e.g., 'Regulation (EU) 2017/745' or 'MDR_19-27.pdf' -> 'MDR'
        """
        target = f"{title} {filename or ''}".upper()
        if "MDR" in target or "MEDICAL DEVICE" in target or "2017/745" in target:
            return "MDR"
        if "ARTIFICIAL INTELLIGENCE" in target or "AI ACT" in target or "2024/1689" in target:
            return "EU_AI_ACT"
        if "GDPR" in target or "DATA PROTECTION" in target or "2016/679" in target:
            return "GDPR"

        if filename:
            name_base = filename.rsplit(".", 1)[0]
            clean_fn = re.sub(r"[^a-zA-Z0-9_]", "_", name_base).strip("_")
            if clean_fn:
                return clean_fn[:20].upper()

        clean = re.sub(r"[^a-zA-Z0-9\s]", "", title)
        parts = clean.split()
        return "_".join(parts[:4]).upper() if parts else "LEGISLATION"

    async def extract(self, text: str, filename: str | None = None) -> ExtractedStructure:
        """
        Extract metadata, terms, and cross-references from legislation text.
        """
        logger.info("Extracting structure from document text", filename=filename)

        title = ""
        for line in text.splitlines():
            line_str = line.strip()
            if line_str and len(line_str) > 10:
                title = line_str
                break

        if not title:
            title = filename or "Legislation Document"

        short_name = self.extract_short_name(title, filename)

        doc_type = "regulation"
        if "directive" in text.lower()[:1000]:
            doc_type = "directive"
        elif "decision" in text.lower()[:1000]:
            doc_type = "decision"

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
