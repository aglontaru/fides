"""
Pydantic models for Fides knowledge graph nodes and relationships.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class RelType(StrEnum):
    """Relationship types in the knowledge graph."""

    CONTAINS = "CONTAINS"
    HAS_CHAPTER = "HAS_CHAPTER"
    HAS_SECTION = "HAS_SECTION"
    HAS_ARTICLE = "HAS_ARTICLE"
    HAS_PARAGRAPH = "HAS_PARAGRAPH"
    HAS_ANNEX = "HAS_ANNEX"
    HAS_RECITAL = "HAS_RECITAL"
    NEXT_ARTICLE = "NEXT_ARTICLE"
    NEXT_PARAGRAPH = "NEXT_PARAGRAPH"
    CITES = "CITES"
    REFERENCES_ANNEX = "REFERENCES_ANNEX"
    INTERPRETED_BY = "INTERPRETED_BY"
    DEFINES = "DEFINES"
    USES_TERM = "USES_TERM"
    IMPOSES = "IMPOSES"
    APPLIES_TO = "APPLIES_TO"
    AMENDS = "AMENDS"


class DocumentType(StrEnum):
    """Types of EU legislation documents."""

    REGULATION = "regulation"
    DIRECTIVE = "directive"
    DECISION = "decision"


class Modality(StrEnum):
    """Modalities for obligations."""

    SHALL = "shall"
    MUST = "must"
    MAY = "may"


class GraphNode(BaseModel):
    """Base class for all graph nodes."""

    id: str

    def to_neo4j_properties(self) -> dict[str, Any]:
        """Convert the model to a dictionary suitable for Neo4j operations."""
        props = self.model_dump(exclude_none=True)
        # Convert datetimes to ISO format strings for Neo4j compatibility
        for key, value in props.items():
            if isinstance(value, datetime):
                props[key] = value.isoformat()
        return props


class DocumentNode(GraphNode):
    """Top-level regulation document."""

    title: str
    short_name: str
    document_type: DocumentType
    publication_date: datetime | None = None
    content_hash: str
    indexed_at: datetime = Field(default_factory=datetime.now)
    version: str | None = None
    eli_uri: str | None = None


class RecitalNode(GraphNode):
    """Preamble item."""

    number: str
    text: str
    embedding: list[float] | None = None


class ChapterNode(GraphNode):
    """Chapter within a document."""

    number: str
    title: str | None = None


class SectionNode(GraphNode):
    """Section within a chapter."""

    number: str
    title: str | None = None


class ArticleNode(GraphNode):
    """Article within a document."""

    number: str
    title: str | None = None
    full_text: str
    embedding: list[float] | None = None
    content_hash: str


class ParagraphNode(GraphNode):
    """Paragraph within an article."""

    number: str
    text: str
    embedding: list[float] | None = None
    content_hash: str


class AnnexNode(GraphNode):
    """Annex document."""

    number: str
    title: str | None = None
    text: str
    embedding: list[float] | None = None


class DefinedTermNode(GraphNode):
    """A term defined within the legislation."""

    term: str
    normalized_term: str
    definition: str


class ObligationNode(GraphNode):
    """An obligation imposed by the legislation."""

    modality: Modality
    description: str


class ActorRoleNode(GraphNode):
    """An actor role mentioned in the legislation."""

    name: str
