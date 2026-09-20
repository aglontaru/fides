"""Tests for graph models."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from fides.graph.models import (
    ArticleNode,
    DocumentNode,
    DocumentType,
    ParagraphNode,
    RelType,
)


@pytest.mark.unit
def test_document_node_creation():
    """Test DocumentNode creation and validation."""
    doc = DocumentNode(
        id="EU_AI_ACT_2024",
        title="AI Act",
        short_name="EU AI Act",
        document_type=DocumentType.REGULATION,
        content_hash="abc123hash",
    )
    assert doc.id == "EU_AI_ACT_2024"
    assert doc.content_hash == "abc123hash"
    assert doc.document_type == DocumentType.REGULATION


@pytest.mark.unit
def test_article_node_id_pattern():
    """Test ArticleNode fields and pattern."""
    art = ArticleNode(
        id="EU_AI_ACT:art:1",
        number="1",
        title="Subject matter",
        full_text="Article 1 content...",
        content_hash="hash1",
    )
    assert art.id.startswith("EU_AI_ACT:art:")
    assert art.number == "1"


@pytest.mark.unit
def test_paragraph_node_id_pattern():
    """Test ParagraphNode creation."""
    para = ParagraphNode(
        id="EU_AI_ACT:art:1:para:1",
        number="1",
        text="Content paragraph 1",
        content_hash="hashpara1",
    )
    assert para.id.startswith("EU_AI_ACT:art:1:para:")
    assert para.number == "1"


@pytest.mark.unit
def test_to_neo4j_properties():
    """Test to_neo4j_properties() returns correct dict."""
    doc = DocumentNode(
        id="doc_1",
        title="Test Doc",
        short_name="TD",
        document_type=DocumentType.REGULATION,
        content_hash="abc123hash",
        publication_date=datetime(2024, 7, 12, tzinfo=UTC),
    )
    props = doc.to_neo4j_properties()
    assert props["id"] == "doc_1"
    assert props["content_hash"] == "abc123hash"
    assert props["document_type"] == "regulation"
    assert "2024-07-12" in props["publication_date"]


@pytest.mark.unit
def test_model_field_validation():
    """Test model field validation (required fields)."""
    with pytest.raises(ValidationError):
        DocumentNode(id="doc_1")  # Missing title, short_name, document_type, content_hash


@pytest.mark.unit
def test_rel_type_enum():
    """Test RelType enum values."""
    assert RelType.CONTAINS == "CONTAINS"
    assert RelType.HAS_ARTICLE == "HAS_ARTICLE"
    assert RelType.HAS_PARAGRAPH == "HAS_PARAGRAPH"
    assert RelType.CITES == "CITES"
