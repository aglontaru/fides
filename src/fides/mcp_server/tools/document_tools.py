"""Document processing tools."""

from __future__ import annotations

import base64
import hashlib
import json

import pymupdf as fitz
import structlog

from fides.mcp_server.server import mcp

logger = structlog.get_logger(__name__)


@mcp.tool()
async def parse_document(content_base64: str, filename: str) -> str:
    """Parse a base64-encoded PDF or plain text file.

    Args:
        content_base64: Base64 encoded file content.
        filename: Name of the file, used to detect type.

    Returns:
        JSON string containing parsed text or error.
    """
    logger.info("Parsing document", filename=filename)
    try:
        content_bytes = base64.b64decode(content_base64)

        if filename.lower().endswith(".pdf") or content_bytes.startswith(b"%PDF"):
            text = ""
            with fitz.open(stream=content_bytes, filetype="pdf") as doc:
                for page in doc:
                    text += page.get_text() + "\n"
            return json.dumps({"status": "success", "text": text.strip()})
        else:
            # Assume plain text
            text = content_bytes.decode("utf-8")
            return json.dumps({"status": "success", "text": text.strip()})

    except Exception as e:
        logger.error("Document parsing failed", error=str(e))
        return json.dumps({"status": "error", "error": str(e)})


@mcp.tool()
async def chunk_legislation(parsed_text: str, document_title: str, short_name: str) -> str:
    """Split legislation text into hierarchical chunks.

    Args:
        parsed_text: Full parsed text of the document.
        document_title: Title of the document.
        short_name: Short name of the document.

    Returns:
        JSON string representing the hierarchy.
    """
    logger.info("Chunking legislation", short_name=short_name)
    try:
        from fides.ingestion.chunkers.legislation import LegislationChunker

        chunker = LegislationChunker(short_name=short_name, document_title=document_title)
        result = await chunker.chunk(parsed_text)
        return json.dumps(
            {
                "status": "success",
                "document_title": result.document_title,
                "short_name": result.short_name,
                "chunks_count": len(result.chunks),
                "chunks": [chunk.model_dump() for chunk in result.chunks],
                "hierarchy": result.hierarchy,
            }
        )
    except Exception as e:
        logger.error("Chunking failed", error=str(e))
        return json.dumps({"status": "error", "error": str(e)})


@mcp.tool()
async def extract_structure(parsed_text: str, filename: str | None = None) -> str:
    """Extract metadata, defined terms, and cross-references from text.

    Args:
        parsed_text: Parsed legislation text.
        filename: Optional filename of the document.

    Returns:
        JSON string containing extracted structure.
    """
    logger.info("Extracting structure from text", filename=filename)
    try:
        from fides.ingestion.extractors.structure import StructureExtractor

        extractor = StructureExtractor()
        structure = await extractor.extract(parsed_text, filename=filename)
        return json.dumps(
            {
                "status": "success",
                "structure": structure.model_dump(),
            }
        )
    except Exception as e:
        logger.error("Extraction failed", error=str(e))
        return json.dumps({"status": "error", "error": str(e)})


@mcp.tool()
async def compute_content_hash(text: str) -> str:
    """Compute SHA-256 hash of normalized text.

    Args:
        text: Input text to hash.

    Returns:
        JSON string containing the hash.
    """
    try:
        normalized = text.strip()
        hash_val = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        return json.dumps({"status": "success", "hash": hash_val})
    except Exception as e:
        logger.error("Hash computation failed", error=str(e))
        return json.dumps({"status": "error", "error": str(e)})


@mcp.tool()
async def ingest_document(content_base64: str, filename: str) -> str:
    """Full end-to-end document ingestion: parse, chunk, dedup, embed, persist.

    Wraps the IngestionPipeline for safe, transactional document ingestion.

    Args:
        content_base64: Base64-encoded PDF or text file content.
        filename: Name of the file (e.g., 'eu_ai_act.pdf').

    Returns:
        JSON string containing ingestion status and statistics.
    """
    logger.info("Ingesting document via MCP tool", filename=filename)
    try:
        from fides.config.settings import get_settings
        from fides.ingestion import IngestionPipeline
        from fides.mcp_server.dependencies import deps

        driver = await deps.get_neo4j_driver()
        pipeline = IngestionPipeline(driver=driver, settings=get_settings())
        content_bytes = base64.b64decode(content_base64)
        result = await pipeline.ingest_pdf_bytes(content_bytes, filename)
        return json.dumps({"status": "success", "data": result.to_dict()})
    except Exception as e:
        logger.error("Ingestion failed", filename=filename, error=str(e))
        return json.dumps({"status": "error", "error": str(e)})
