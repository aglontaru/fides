"""
Neo4j graph layer for the Fides legislation knowledge graph.
"""

from __future__ import annotations

from .models import (
    ActorRoleNode,
    AnnexNode,
    ArticleNode,
    ChapterNode,
    DefinedTermNode,
    DocumentNode,
    DocumentType,
    GraphNode,
    Modality,
    ObligationNode,
    ParagraphNode,
    RecitalNode,
    RelType,
    SectionNode,
)
from .operations import (
    create_cross_reference,
    delete_document_graph,
    find_document_by_hash,
    find_document_by_name,
    get_article,
    get_article_with_context,
    get_document_articles,
    get_graph_stats,
    upsert_article,
    upsert_document,
    upsert_paragraph,
)
from .schema import get_schema_statements, initialize_schema

__all__ = [
    "ActorRoleNode",
    "AnnexNode",
    "ArticleNode",
    "ChapterNode",
    "DefinedTermNode",
    "DocumentNode",
    "DocumentType",
    "GraphNode",
    "Modality",
    "ObligationNode",
    "ParagraphNode",
    "RecitalNode",
    "RelType",
    "SectionNode",
    "create_cross_reference",
    "delete_document_graph",
    "find_document_by_hash",
    "find_document_by_name",
    "get_article",
    "get_article_with_context",
    "get_document_articles",
    "get_graph_stats",
    "get_schema_statements",
    "initialize_schema",
    "upsert_article",
    "upsert_document",
    "upsert_paragraph",
]
