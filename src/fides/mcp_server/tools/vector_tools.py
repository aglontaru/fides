"""Vector search and embedding tools."""

from __future__ import annotations

import json
from typing import Any

import structlog

from fides.mcp_server.dependencies import deps
from fides.mcp_server.server import mcp

logger = structlog.get_logger(__name__)


@mcp.tool()
async def vector_search(query_text: str, top_k: int = 5, node_type: str = "Paragraph") -> str:
    """Embed query, search Neo4j vector index, return results with scores.

    DO NOT call this tool for greetings, pleasantries, or general chat.
    ONLY call this tool when searching for specific paragraph or article text in the legislation knowledge graph.

    Args:
        query_text: The semantic search query.
        top_k: Number of results to return.
        node_type: Type of node to search (e.g., 'Paragraph').

    Returns:
        JSON string of matching nodes and their scores.
    """
    logger.info("Performing vector search", query=query_text, top_k=top_k)
    try:
        embeddings_model = deps.get_embeddings()
        vector = await embeddings_model.aembed_query(query_text)

        index_name = f"vector_{node_type}"

        cypher = (
            "CALL db.index.vector.queryNodes($index_name, $top_k, $vector) "
            "YIELD node, score "
            "RETURN node.id AS id, node.text AS text, score"
        )
        driver = await deps.get_neo4j_driver()
        async with driver.session() as session:
            result = await session.run(
                cypher, {"index_name": index_name, "top_k": top_k, "vector": vector}
            )
            records = [record.data() async for record in result]

        return json.dumps({"status": "success", "data": records})
    except Exception as e:
        logger.error("Vector search failed", error=str(e))
        return json.dumps({"status": "error", "error": str(e)})


@mcp.tool()
async def hybrid_search(query_text: str, top_k: int = 8) -> str:
    """Combined vector + fulltext + graph context expansion RAG retrieval tool.

    Searches legislative Paragraphs, Articles, and Recitals using both vector
    embeddings and fulltext keyword matching, then expands context via graph
    relationships.

    DO NOT call this tool for greetings, pleasantries, small talk, or queries
    unrelated to legal provisions.
    ONLY call this tool when the user asks a substantive question about
    legislation, regulations, articles, recitals, or legal compliance.

    Args:
        query_text: The semantic search query.
        top_k: Number of provisions to retrieve per index before merging.

    Returns:
        JSON string containing structured RAG context.
    """
    logger.info("Performing hybrid RAG search", query=query_text)
    try:
        embeddings_model = deps.get_embeddings()
        vector = await embeddings_model.aembed_query(query_text)
        driver = await deps.get_neo4j_driver()

        combined_records: list[dict[str, Any]] = []

        async with driver.session() as session:
            # 1. Vector search: Paragraphs
            cypher_para = (
                "CALL db.index.vector.queryNodes('vector_Paragraph', $top_k, $vector) "
                "YIELD node AS p, score "
                "MATCH (a:Article)-[:HAS_PARAGRAPH]->(p) "
                "OPTIONAL MATCH (d:Document)-[:HAS_ARTICLE*]->(a) "
                "OPTIONAL MATCH (c:Chapter)-[:HAS_ARTICLE]->(a) "
                "OPTIONAL MATCH (a)-[:CITES]->(ca:Article) "
                "RETURN 'paragraph' AS type, "
                "       p.id AS paragraph_id, "
                "       p.id AS provision_id, "
                "       p.text AS paragraph_text, "
                "       p.text AS text, "
                "       score, "
                "       a.id AS article_id, "
                "       a.title AS article_title, "
                "       coalesce(d.short_name, d.title, '') AS document, "
                "       c.title AS chapter_title, "
                "       collect(DISTINCT ca.id) AS cited_articles "
                "ORDER BY score DESC"
            )
            try:
                result_para = await session.run(cypher_para, {"top_k": top_k, "vector": vector})
                para_records = [record.data() async for record in result_para]
                combined_records.extend(para_records)
            except Exception as pe:
                logger.warning("Paragraph vector search failed", error=str(pe))

            # 2. Vector search: Articles (many articles have no child paragraphs)
            cypher_art = (
                "CALL db.index.vector.queryNodes('vector_Article', $top_k, $vector) "
                "YIELD node AS a, score "
                "OPTIONAL MATCH (d:Document)-[:HAS_ARTICLE*]->(a) "
                "OPTIONAL MATCH (c:Chapter)-[:HAS_ARTICLE]->(a) "
                "OPTIONAL MATCH (a)-[:CITES]->(ca:Article) "
                "RETURN 'article' AS type, "
                "       a.id AS paragraph_id, "
                "       a.id AS provision_id, "
                "       a.full_text AS paragraph_text, "
                "       a.full_text AS text, "
                "       score, "
                "       a.id AS article_id, "
                "       a.title AS article_title, "
                "       coalesce(d.short_name, d.title, '') AS document, "
                "       coalesce(c.title, '') AS chapter_title, "
                "       collect(DISTINCT ca.id) AS cited_articles "
                "ORDER BY score DESC"
            )
            try:
                result_art = await session.run(cypher_art, {"top_k": top_k, "vector": vector})
                art_records = [record.data() async for record in result_art]
                combined_records.extend(art_records)
            except Exception as ae:
                logger.warning("Article vector search failed", error=str(ae))

            # 3. Vector search: Recitals
            cypher_rec = (
                "CALL db.index.vector.queryNodes('vector_Recital', $top_k, $vector) "
                "YIELD node AS r, score "
                "OPTIONAL MATCH (d:Document)-[:HAS_RECITAL]->(r) "
                "RETURN 'recital' AS type, "
                "       r.id AS paragraph_id, "
                "       r.id AS provision_id, "
                "       r.text AS paragraph_text, "
                "       r.text AS text, "
                "       score, "
                "       r.id AS article_id, "
                "       coalesce(r.title, 'Recital (' + coalesce(r.number, '') + ')') AS article_title, "
                "       coalesce(d.short_name, d.title, '') AS document, "
                "       '' AS chapter_title, "
                "       [] AS cited_articles "
                "ORDER BY score DESC"
            )
            try:
                result_rec = await session.run(cypher_rec, {"top_k": top_k, "vector": vector})
                rec_records = [record.data() async for record in result_rec]
                combined_records.extend(rec_records)
            except Exception as re_err:
                logger.warning("Recital vector search failed", error=str(re_err))

            # 4. Fulltext keyword fallback: articles
            # Extracts key terms for exact matching (catches exemption language)
            ft_query = _build_fulltext_query(query_text)
            if ft_query:
                cypher_ft_art = (
                    "CALL db.index.fulltext.queryNodes('article_text', $query) "
                    "YIELD node AS a, score "
                    "WHERE score > 1.5 "
                    "OPTIONAL MATCH (d:Document)-[:HAS_ARTICLE*]->(a) "
                    "OPTIONAL MATCH (c:Chapter)-[:HAS_ARTICLE]->(a) "
                    "RETURN 'article_ft' AS type, "
                    "       a.id AS paragraph_id, "
                    "       a.id AS provision_id, "
                    "       a.full_text AS paragraph_text, "
                    "       a.full_text AS text, "
                    "       score * 0.1 AS score, "  # Normalize FT score to ~0-1 range
                    "       a.id AS article_id, "
                    "       a.title AS article_title, "
                    "       coalesce(d.short_name, d.title, '') AS document, "
                    "       coalesce(c.title, '') AS chapter_title, "
                    "       [] AS cited_articles "
                    "ORDER BY score DESC "
                    "LIMIT $top_k"
                )
                try:
                    result_ft = await session.run(
                        cypher_ft_art, {"query": ft_query, "top_k": top_k}
                    )
                    ft_records = [record.data() async for record in result_ft]
                    combined_records.extend(ft_records)
                except Exception as ft_err:
                    logger.warning("Fulltext article search failed", error=str(ft_err))

                # 5. Fulltext keyword fallback: paragraphs
                cypher_ft_para = (
                    "CALL db.index.fulltext.queryNodes('paragraph_text', $query) "
                    "YIELD node AS p, score "
                    "WHERE score > 1.5 "
                    "MATCH (a:Article)-[:HAS_PARAGRAPH]->(p) "
                    "OPTIONAL MATCH (d:Document)-[:HAS_ARTICLE*]->(a) "
                    "RETURN 'paragraph_ft' AS type, "
                    "       p.id AS paragraph_id, "
                    "       p.id AS provision_id, "
                    "       p.text AS paragraph_text, "
                    "       p.text AS text, "
                    "       score * 0.1 AS score, "
                    "       a.id AS article_id, "
                    "       a.title AS article_title, "
                    "       coalesce(d.short_name, d.title, '') AS document, "
                    "       '' AS chapter_title, "
                    "       [] AS cited_articles "
                    "ORDER BY score DESC "
                    "LIMIT $top_k"
                )
                try:
                    result_ft_p = await session.run(
                        cypher_ft_para, {"query": ft_query, "top_k": top_k}
                    )
                    ft_p_records = [record.data() async for record in result_ft_p]
                    combined_records.extend(ft_p_records)
                except Exception as ft_p_err:
                    logger.warning("Fulltext paragraph search failed", error=str(ft_p_err))

        # Deduplicate and sort by score descending
        seen_ids: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for rec in sorted(combined_records, key=lambda x: x.get("score", 0.0), reverse=True):
            pid = rec.get("provision_id", "")
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                deduped.append(rec)

        top_results = deduped[: top_k * 2]  # Return more results for multi-query merging
        logger.info(
            "Hybrid search complete",
            total_candidates=len(combined_records),
            deduped=len(deduped),
            returned=len(top_results),
        )
        return json.dumps({"status": "success", "data": top_results})
    except Exception as e:
        logger.error("Hybrid search failed", error=str(e))
        return json.dumps({"status": "error", "error": str(e)})


def _build_fulltext_query(query_text: str) -> str:
    """Extract key legal terms from query for fulltext index search.

    Builds a Lucene query string targeting legal domain terms that
    semantic embeddings often miss (exemptions, negative clauses).
    """
    # Extract meaningful multi-word and legal terms
    query_lower = query_text.lower()
    ft_terms: list[str] = []

    # Legal domain keywords to always search if present
    legal_keywords = [
        "custom-made", "investigational", "exemption", "exempt", "exception",
        "shall not", "does not apply", "other than", "excluded",
        "CE marking", "UDI", "conformity", "declaration", "notified body",
        "authorised representative", "authorized representative",
        "importer", "liability", "joint", "Annex XIII", "Annex IX",
        "SSCP", "safety and clinical performance",
    ]
    for kw in legal_keywords:
        if kw.lower() in query_lower:
            ft_terms.append(f'"{kw}"')

    # Also add significant individual words (>3 chars, not stopwords)
    stopwords = {
        "the", "and", "for", "are", "with", "from", "that", "this", "which",
        "what", "does", "how", "who", "when", "where", "about", "their",
        "have", "been", "being", "into", "across", "between", "specific",
        "specifically", "identify", "exact", "requirements", "obligations",
    }
    for word in query_text.split():
        clean = word.strip(".,;:!?()[]\"'").lower()
        if len(clean) > 3 and clean not in stopwords and clean not in [t.strip('"').lower() for t in ft_terms]:
            ft_terms.append(clean)

    return " OR ".join(ft_terms) if ft_terms else ""


@mcp.tool()
async def vector_upsert(node_id: str, text: str, node_label: str = "Paragraph") -> str:
    """Generate embedding for text and store it on the specified node.

    Args:
        node_id: The ID of the node.
        text: The text to embed.
        node_label: The label of the node (default 'Paragraph').

    Returns:
        JSON string with success status or error.
    """
    logger.info("Upserting vector", node_id=node_id, label=node_label)
    try:
        embeddings_model = deps.get_embeddings()
        vector = await embeddings_model.aembed_query(text)

        cypher = (
            f"MATCH (n:{node_label} {{id: $node_id}}) SET n.embedding = $vector RETURN n.id AS id"
        )
        driver = await deps.get_neo4j_driver()
        async with driver.session() as session:
            result = await session.run(cypher, {"node_id": node_id, "vector": vector})
            record = await result.single()
            if not record:
                return json.dumps({"status": "error", "error": "Node not found"})

        return json.dumps({"status": "success", "node_id": node_id})
    except Exception as e:
        logger.error("Vector upsert failed", error=str(e))
        return json.dumps({"status": "error", "error": str(e)})
