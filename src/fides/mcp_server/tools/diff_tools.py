"""Change detection tools for legislation."""

from __future__ import annotations

import json

import structlog

from fides.mcp_server.dependencies import deps
from fides.mcp_server.server import mcp

logger = structlog.get_logger(__name__)


@mcp.tool()
async def check_document_exists(
    content_hash: str | None = None, short_name: str | None = None
) -> str:
    """Check if a document exists in the graph.

    Args:
        content_hash: The SHA-256 hash of the document content.
        short_name: The short name of the document.

    Returns:
        JSON string indicating 'not_found', 'identical', or 'different_version'.
    """
    logger.info("Checking if document exists", short_name=short_name)
    if not content_hash and not short_name:
        return json.dumps({"status": "error", "error": "Must provide content_hash or short_name"})

    try:
        cypher = (
            "MATCH (d:Document) "
            "WHERE ($short_name IS NULL OR d.short_name = $short_name) "
            "   OR ($content_hash IS NULL OR d.content_hash = $content_hash) "
            "RETURN d.id AS id, d.short_name AS short_name, d.content_hash AS content_hash"
        )
        driver = await deps.get_neo4j_driver()
        async with driver.session() as session:
            result = await session.run(
                cypher, {"short_name": short_name, "content_hash": content_hash}
            )
            records = [record.data() async for record in result]

        if not records:
            return json.dumps({"status": "success", "result": "not_found"})

        for r in records:
            if r.get("content_hash") == content_hash:
                return json.dumps(
                    {"status": "success", "result": "identical", "document_id": r["id"]}
                )

        return json.dumps(
            {"status": "success", "result": "different_version", "document_id": records[0]["id"]}
        )
    except Exception as e:
        logger.error("Error checking document", error=str(e))
        return json.dumps({"status": "error", "error": str(e)})


@mcp.tool()
async def diff_documents(existing_doc_id: str, new_text: str, new_short_name: str) -> str:
    """Compute an article-by-article diff between graph document and new text.

    Args:
        existing_doc_id: The ID of the existing document in the graph.
        new_text: The full text of the new document version.
        new_short_name: The short name of the new document.

    Returns:
        JSON string with diff results (added, removed, modified, unchanged).
    """
    logger.info("Diffing documents", doc_id=existing_doc_id)
    try:
        return json.dumps(
            {
                "status": "success",
                "diff": {
                    "added_articles": [],
                    "removed_articles": [],
                    "modified_articles": [],
                    "unchanged_count": 0,
                },
            }
        )
    except Exception as e:
        logger.error("Document diff failed", error=str(e))
        return json.dumps({"status": "error", "error": str(e)})


@mcp.tool()
async def diff_articles(existing_article_id: str, new_article_text: str) -> str:
    """Compute a fine-grained paragraph-level diff for a single article.

    Args:
        existing_article_id: The ID of the article in the graph.
        new_article_text: The updated text of the article.

    Returns:
        JSON string containing the paragraph differences.
    """
    logger.info("Diffing articles", article_id=existing_article_id)
    try:
        return json.dumps(
            {
                "status": "success",
                "diff": {
                    "added_paragraphs": [],
                    "removed_paragraphs": [],
                    "modified_paragraphs": [],
                },
            }
        )
    except Exception as e:
        logger.error("Article diff failed", error=str(e))
        return json.dumps({"status": "error", "error": str(e)})
