"""Tests for the legislation chunker."""

from __future__ import annotations

import pytest

from fides.ingestion.chunkers.legislation import LegislationChunker


@pytest.fixture
def chunker() -> LegislationChunker:
    return LegislationChunker(short_name="EU_AI_ACT", document_title="EU AI Act")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_detection_of_article_boundaries(chunker: LegislationChunker):
    """Test detection of Article boundaries."""
    text = "Article 1 Subject Matter\nContent 1\nArticle 2 Scope\nContent 2"
    res = await chunker.chunk(text)
    article_chunks = [c for c in res.chunks if c.chunk_type == "article"]
    assert len(article_chunks) == 2
    assert article_chunks[0].number == "1"
    assert article_chunks[1].number == "2"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_detection_of_numbered_paragraphs(chunker: LegislationChunker):
    """Test detection of numbered paragraphs within an article."""
    text = "Article 1 Test\n1. First paragraph.\n2. Second paragraph."
    res = await chunker.chunk(text)
    para_chunks = [c for c in res.chunks if c.chunk_type == "paragraph"]
    assert len(para_chunks) == 2
    assert para_chunks[0].parent_id == "EU_AI_ACT:art:1"
    assert "First paragraph" in para_chunks[0].text


@pytest.mark.unit
@pytest.mark.asyncio
async def test_deterministic_id_generation(chunker: LegislationChunker):
    """Test deterministic ID generation."""
    text = "Article 1\nContent"
    res1 = await chunker.chunk(text)
    res2 = await chunker.chunk(text)
    assert res1.chunks[0].id == res2.chunks[0].id
    assert res1.chunks[0].id == "EU_AI_ACT:art:1"


@pytest.mark.unit
def test_cross_reference_detection(chunker: LegislationChunker):
    """Test cross-reference extraction method."""
    text = "As provided for in Article 6 and Article 16, obligations apply."
    refs = chunker.extract_cross_references(text)
    assert "EU_AI_ACT:art:6" in refs
    assert "EU_AI_ACT:art:16" in refs


@pytest.mark.unit
@pytest.mark.asyncio
async def test_full_chunking_of_realistic_excerpt(
    chunker: LegislationChunker, sample_legislation_text: str
):
    """Test full chunking of realistic EU AI Act excerpt."""
    res = await chunker.chunk(sample_legislation_text)
    assert len(res.chunks) > 0
    article_chunks = [c for c in res.chunks if c.chunk_type == "article"]
    assert len(article_chunks) >= 3
    # Check that hierarchy holds root or articles
    assert "EU_AI_ACT:art:1" in res.hierarchy
