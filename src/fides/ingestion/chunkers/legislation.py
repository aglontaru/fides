"""
Legislation-aware chunker that understands EU legal document structure.
"""

from __future__ import annotations

import re
from typing import Any

import structlog
from pydantic import BaseModel

logger = structlog.get_logger(__name__)


class LegislationChunk(BaseModel):
    """A structured chunk of legislation."""

    id: str
    chunk_type: str
    number: int | str
    title: str | None = None
    text: str
    parent_id: str | None = None
    children_ids: list[str] = []
    cross_references: list[str] = []
    metadata: dict[str, Any] = {}


class ChunkedLegislation(BaseModel):
    """The complete chunked legislation document."""

    document_title: str
    short_name: str
    chunks: list[LegislationChunk]
    hierarchy: dict[str, list[str]]


class LegislationChunker:
    """Chunker that parses EU legislation into a hierarchical structure."""

    TITLE_PATTERN = re.compile(
        r"^\s*TITLE\s+([IVXLCDM]+|[0-9]+)\s*(.*)$", re.IGNORECASE | re.MULTILINE
    )
    CHAPTER_PATTERN = re.compile(
        r"^\s*CHAPTER\s+([IVXLCDM]+|[0-9]+)\s*(.*)$", re.IGNORECASE | re.MULTILINE
    )
    SECTION_PATTERN = re.compile(
        r"^\s*SECTION\s+([0-9]+|[IVXLCDM]+)\s*(.*)$", re.IGNORECASE | re.MULTILINE
    )
    ARTICLE_PATTERN = re.compile(
        r"^\s*Article\s+([0-9]+[a-z]?)\s*(.*)$", re.IGNORECASE | re.MULTILINE
    )
    PARAGRAPH_PATTERN = re.compile(r"^\s*(?:(\d+)\.|(\(\d+\)))\s+(.*)$", re.MULTILINE)
    POINT_PATTERN = re.compile(r"^\s*\(([a-z]+)\)\s+(.*)$", re.MULTILINE)
    ANNEX_PATTERN = re.compile(
        r"^\s*ANNEX\s+([IVXLCDM]+|[0-9]+)\s*(.*)$", re.IGNORECASE | re.MULTILINE
    )
    RECITAL_PATTERN = re.compile(r"^\s*\((\d+)\)\s+(.*)$", re.MULTILINE)

    CROSS_REF_PATTERN = re.compile(
        r"(?:Article|Articles)\s+([0-9]+[a-z]?(?:\s+and\s+[0-9]+[a-z]?)*)", re.IGNORECASE
    )

    def __init__(self, short_name: str, document_title: str) -> None:
        self.short_name = short_name
        self.document_title = document_title

    def extract_cross_references(self, text: str) -> list[str]:
        """Extract cross-references to other articles from text."""
        refs = []
        for match in self.CROSS_REF_PATTERN.finditer(text):
            ref_str = match.group(1).strip()
            parts = re.split(r"\s+and\s+|,", ref_str)
            for part in parts:
                part = part.strip()
                if part:
                    refs.append(f"{self.short_name}:art:{part}")
        return refs

    async def chunk(self, text: str) -> ChunkedLegislation:
        """
        Chunk the raw legislation text into a hierarchical structure.
        """
        logger.info(f"Starting to chunk legislation: {self.short_name}")
        chunks: list[LegislationChunk] = []
        hierarchy: dict[str, list[str]] = {}

        lines = text.split("\n")

        current_title = None
        current_chapter = None
        current_section = None
        current_article = None
        current_paragraph = None

        current_buffer: list[str] = []
        current_node_id = None
        current_node_type = None
        current_node_number: str | int = ""
        current_node_title = None

        root_id = f"{self.short_name}:root"
        hierarchy[root_id] = []

        def save_buffer(parent_id: str | None = None) -> None:
            nonlocal \
                current_buffer, \
                current_node_id, \
                current_node_type, \
                current_node_number, \
                current_node_title
            if current_buffer and current_node_id:
                chunk_text = "\n".join(current_buffer).strip()
                if chunk_text:
                    refs = self.extract_cross_references(chunk_text)
                    chunk = LegislationChunk(
                        id=current_node_id,
                        chunk_type=current_node_type or "unknown",
                        number=current_node_number,
                        title=current_node_title,
                        text=chunk_text,
                        parent_id=parent_id,
                        cross_references=refs,
                    )
                    chunks.append(chunk)
                    if parent_id:
                        if parent_id not in hierarchy:
                            hierarchy[parent_id] = []
                        hierarchy[parent_id].append(current_node_id)
            current_buffer = []

        for line in lines:
            if not line.strip():
                continue

            art_match = self.ARTICLE_PATTERN.match(line)
            if art_match:
                save_buffer(current_section or current_chapter or current_title or root_id)
                num = art_match.group(1)
                title = art_match.group(2).strip()
                current_article = f"{self.short_name}:art:{num}"
                current_node_id = current_article
                current_node_type = "article"
                current_node_number = num
                current_node_title = title if title else None
                current_paragraph = None
                continue

            if not current_article:
                recital_match = self.RECITAL_PATTERN.match(line)
                if recital_match:
                    save_buffer(root_id)
                    num = recital_match.group(1)
                    text_part = recital_match.group(2).strip()
                    current_node_id = f"{self.short_name}:recital:{num}"
                    current_node_type = "recital"
                    current_node_number = num
                    current_node_title = f"Recital ({num})"
                    if text_part:
                        current_buffer.append(text_part)
                    continue

            para_match = self.PARAGRAPH_PATTERN.match(line)
            if para_match and current_article:
                save_buffer(current_article)
                num = para_match.group(1) or para_match.group(2).strip("()")
                current_paragraph = f"{current_article}:para:{num}"
                current_node_id = current_paragraph
                current_node_type = "paragraph"
                current_node_number = num
                current_node_title = None
                current_buffer.append(para_match.group(3))
                continue

            if current_node_id:
                current_buffer.append(line)
            else:
                current_node_id = f"{self.short_name}:preamble"
                current_node_type = "preamble"
                current_node_number = ""
                current_buffer.append(line)

        save_buffer(
            current_article or current_section or current_chapter or current_title or root_id
        )

        return ChunkedLegislation(
            document_title=self.document_title,
            short_name=self.short_name,
            chunks=chunks,
            hierarchy=hierarchy,
        )
