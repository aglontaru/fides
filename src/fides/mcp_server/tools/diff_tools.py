"""Change detection tools for legislation."""

from __future__ import annotations

import json
from typing import Any

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


def _cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Compute cosine similarity between two float vectors."""
    dot = sum(a * b for a, b in zip(v1, v2, strict=False))
    norm1 = sum(a * a for a in v1) ** 0.5
    norm2 = sum(b * b for b in v2) ** 0.5
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return float(dot / (norm1 * norm2))


@mcp.tool()
async def diff_documents(existing_doc_id: str, new_text: str, new_short_name: str) -> str:
    """Compute an article-by-article semantic diff between graph document and new text.

    Args:
        existing_doc_id: The ID or short name of the existing document in the graph.
        new_text: The full text of the new document version.
        new_short_name: The short name of the new document.

    Returns:
        JSON string with diff results (added, removed, modified with semantic similarity, unchanged).
    """
    logger.info("Diffing documents with semantic comparison", doc_id=existing_doc_id)
    try:
        import hashlib

        from fides.ingestion.chunkers.legislation import LegislationChunker

        # 1. Fetch existing articles from Neo4j
        cypher = (
            "MATCH (d:Document) "
            "WHERE d.id = $doc_id OR d.short_name = $doc_id "
            "OPTIONAL MATCH (d)-[:HAS_ARTICLE|CONTAINS*]->(a:Article) "
            "RETURN a.id AS id, a.number AS number, a.title AS title, "
            "       a.full_text AS full_text, a.content_hash AS content_hash, a.embedding AS embedding "
            "ORDER BY a.number"
        )
        driver = await deps.get_neo4j_driver()
        async with driver.session() as session:
            result = await session.run(cypher, {"doc_id": existing_doc_id})
            existing_records = [record.data() async for record in result]

        existing_articles: dict[str, dict[str, Any]] = {}
        for r in existing_records:
            if r.get("id") and r.get("number"):
                existing_articles[str(r["number"])] = r

        # 2. Chunk new text into articles
        chunker = LegislationChunker(short_name=new_short_name, document_title=new_short_name)
        chunk_res = await chunker.chunk(new_text)

        new_articles: dict[str, dict[str, Any]] = {}
        for chunk in chunk_res.chunks:
            if chunk.chunk_type == "article" and chunk.number:
                c_hash = hashlib.sha256(chunk.text.strip().encode("utf-8")).hexdigest()
                new_articles[str(chunk.number)] = {
                    "number": str(chunk.number),
                    "title": chunk.title,
                    "text": chunk.text,
                    "content_hash": c_hash,
                }

        # 3. Compare existing vs new
        added_articles: list[dict[str, Any]] = []
        removed_articles: list[dict[str, Any]] = []
        modified_articles: list[dict[str, Any]] = []
        unchanged_count = 0

        embeddings = deps.get_embeddings()

        # Check for added and modified
        for num, new_art in new_articles.items():
            if num not in existing_articles:
                added_articles.append(
                    {
                        "article_number": num,
                        "title": new_art.get("title", ""),
                        "text_length": len(new_art.get("text", "")),
                    }
                )
            else:
                old_art = existing_articles[num]
                old_hash = old_art.get("content_hash", "")
                new_hash = new_art.get("content_hash", "")

                if old_hash and new_hash and old_hash == new_hash:
                    unchanged_count += 1
                else:
                    # Semantic comparison
                    old_text = old_art.get("full_text") or ""
                    new_art_text = new_art.get("text") or ""

                    sim = 1.0
                    try:
                        old_vec = old_art.get("embedding")
                        if not old_vec and old_text:
                            old_vec = embeddings.embed_query(old_text)
                        new_vec = embeddings.embed_query(new_art_text) if new_art_text else None
                        if old_vec and new_vec:
                            sim = _cosine_similarity(old_vec, new_vec)
                    except Exception as emb_err:
                        logger.warning("Failed to compute embedding similarity", error=str(emb_err))

                    change_level = (
                        "formatting_or_minor"
                        if sim >= 0.95
                        else ("moderate" if sim >= 0.80 else "major_rewrite")
                    )

                    modified_articles.append(
                        {
                            "article_number": num,
                            "title": new_art.get("title", "") or old_art.get("title", ""),
                            "semantic_similarity": round(sim, 4),
                            "change_level": change_level,
                            "old_text_length": len(old_text),
                            "new_text_length": len(new_art_text),
                        }
                    )

        # Check for removed
        for num, old_art in existing_articles.items():
            if num not in new_articles:
                removed_articles.append(
                    {
                        "article_number": num,
                        "title": old_art.get("title", ""),
                        "article_id": old_art.get("id"),
                    }
                )

        return json.dumps(
            {
                "status": "success",
                "diff": {
                    "added_articles": added_articles,
                    "removed_articles": removed_articles,
                    "modified_articles": modified_articles,
                    "unchanged_count": unchanged_count,
                    "total_existing_articles": len(existing_articles),
                    "total_new_articles": len(new_articles),
                },
            }
        )
    except Exception as e:
        logger.error("Document diff failed", error=str(e))
        return json.dumps({"status": "error", "error": str(e)})


@mcp.tool()
async def diff_articles(existing_article_id: str, new_article_text: str) -> str:
    """Compute a fine-grained paragraph-level semantic diff for a single article.

    Args:
        existing_article_id: The ID of the article in the graph (e.g., 'eu_ai_act:art:16').
        new_article_text: The updated text of the article.

    Returns:
        JSON string containing the paragraph differences with semantic similarity scores.
    """
    logger.info(
        "Diffing articles with semantic paragraph comparison", article_id=existing_article_id
    )
    try:
        import re

        # 1. Fetch existing paragraphs from Neo4j
        cypher = (
            "MATCH (a:Article) "
            "WHERE a.id = $article_id OR a.number = $article_id "
            "OPTIONAL MATCH (a)-[:HAS_PARAGRAPH]->(p:Paragraph) "
            "RETURN p.id AS id, p.number AS number, p.text AS text, "
            "       p.content_hash AS content_hash, p.embedding AS embedding "
            "ORDER BY p.number"
        )
        driver = await deps.get_neo4j_driver()
        async with driver.session() as session:
            result = await session.run(cypher, {"article_id": existing_article_id})
            existing_records = [record.data() async for record in result]

        existing_paragraphs: dict[str, dict[str, Any]] = {}
        for r in existing_records:
            if r.get("id") and r.get("number"):
                existing_paragraphs[str(r["number"])] = r

        # 2. Parse new article text into paragraphs
        # Match standard EU paragraph numbering: "1. Text...", "2. Text..."
        raw_paras = re.split(r"(?:^|\n)\s*(\d+)\.\s+", new_article_text)
        new_paragraphs: dict[str, str] = {}
        if len(raw_paras) > 1:
            for i in range(1, len(raw_paras), 2):
                p_num = raw_paras[i].strip()
                p_text = raw_paras[i + 1].strip() if i + 1 < len(raw_paras) else ""
                new_paragraphs[p_num] = p_text
        else:
            # Fallback: treat non-empty lines as paragraphs
            lines = [line.strip() for line in new_article_text.splitlines() if line.strip()]
            for idx, line in enumerate(lines, 1):
                new_paragraphs[str(idx)] = line

        added_paragraphs: list[dict[str, Any]] = []
        removed_paragraphs: list[dict[str, Any]] = []
        modified_paragraphs: list[dict[str, Any]] = []
        unchanged_paragraphs: list[str] = []

        embeddings = deps.get_embeddings()

        for num, new_p_text in new_paragraphs.items():
            if num not in existing_paragraphs:
                added_paragraphs.append(
                    {
                        "paragraph_number": num,
                        "text": new_p_text,
                    }
                )
            else:
                old_p = existing_paragraphs[num]
                old_p_text = old_p.get("text", "").strip()

                if old_p_text == new_p_text:
                    unchanged_paragraphs.append(num)
                else:
                    sim = 1.0
                    try:
                        old_vec = old_p.get("embedding")
                        if not old_vec and old_p_text:
                            old_vec = embeddings.embed_query(old_p_text)
                        new_vec = embeddings.embed_query(new_p_text) if new_p_text else None
                        if old_vec and new_vec:
                            sim = _cosine_similarity(old_vec, new_vec)
                    except Exception as emb_err:
                        logger.warning("Paragraph embedding similarity error", error=str(emb_err))

                    change_level = (
                        "minor_edit"
                        if sim >= 0.95
                        else ("moderate_change" if sim >= 0.80 else "substantive_revision")
                    )

                    modified_paragraphs.append(
                        {
                            "paragraph_number": num,
                            "old_text": old_p_text,
                            "new_text": new_p_text,
                            "semantic_similarity": round(sim, 4),
                            "change_level": change_level,
                        }
                    )

        for num, old_p in existing_paragraphs.items():
            if num not in new_paragraphs:
                removed_paragraphs.append(
                    {
                        "paragraph_number": num,
                        "text": old_p.get("text", ""),
                    }
                )

        return json.dumps(
            {
                "status": "success",
                "diff": {
                    "added_paragraphs": added_paragraphs,
                    "removed_paragraphs": removed_paragraphs,
                    "modified_paragraphs": modified_paragraphs,
                    "unchanged_paragraphs": unchanged_paragraphs,
                },
            }
        )
    except Exception as e:
        logger.error("Article diff failed", error=str(e))
        return json.dumps({"status": "error", "error": str(e)})
