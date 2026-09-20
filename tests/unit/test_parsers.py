"""Tests for document parsers."""

from __future__ import annotations

import pytest

from fides.ingestion.parsers.base import ParsedDocument
from fides.ingestion.parsers.pdf import PDFParser
from fides.ingestion.parsers.text import TextParser


@pytest.mark.unit
@pytest.mark.asyncio
async def test_text_parser_parse() -> None:
    """Test TextParser.parse() with plain legislation text."""
    parser = TextParser()
    doc = await parser.parse("Test legislation content", filename="test.txt")
    assert isinstance(doc, ParsedDocument)
    assert doc.raw_text == "Test legislation content"
    assert doc.source_filename == "test.txt"


@pytest.mark.unit
def test_text_parser_supports() -> None:
    """Test TextParser.supports() content type detection."""
    parser = TextParser()
    assert parser.supports("test.txt", None) is True
    assert parser.supports("test.md", None) is True
    # TextParser is a fallback, so it supports everything
    assert parser.supports(None, "text/plain") is True


@pytest.mark.unit
def test_pdf_parser_supports() -> None:
    """Test PDFParser.supports() for PDF filenames."""
    parser = PDFParser()
    assert parser.supports("document.pdf", None) is True
    assert parser.supports("DOCUMENT.PDF", None) is True
    assert parser.supports("document.txt", None) is False


@pytest.mark.unit
def test_parsed_document_validation() -> None:
    """Test ParsedDocument model validation."""
    doc = ParsedDocument(
        title="Test Doc",
        raw_text="Hello",
        source_filename="test.txt",
        page_count=1,
        metadata={"language": "en"},
    )
    assert doc.raw_text == "Hello"
    assert doc.page_count == 1
    assert doc.metadata["language"] == "en"


@pytest.mark.unit
def test_parsed_document_defaults() -> None:
    """Test ParsedDocument default values."""
    doc = ParsedDocument(title="Test", raw_text="Content")
    assert doc.source_filename is None
    assert doc.page_count is None
    assert doc.metadata == {}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_text_parser_empty_input() -> None:
    """Test handling of empty input."""
    parser = TextParser()
    doc = await parser.parse("", filename="empty.txt")
    assert doc.raw_text == ""
    assert doc.title == "empty.txt"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_text_parser_bytes_input() -> None:
    """Test TextParser handles bytes input."""
    parser = TextParser()
    doc = await parser.parse(b"Bytes content", filename="test.txt")
    assert doc.raw_text == "Bytes content"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_text_parser_no_filename() -> None:
    """Test TextParser with no filename uses default title."""
    parser = TextParser()
    doc = await parser.parse("Some text")
    assert doc.title == "Text Input"
