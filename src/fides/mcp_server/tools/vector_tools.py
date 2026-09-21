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
async def hybrid_search(query_text: str, top_k: int = 15) -> str:
    """Combined vector + fulltext + graph context expansion RAG retrieval tool.

    Searches legislative Paragraphs, Articles, Annexes, and Recitals across any
    jurisdiction using both vector embeddings and universal fulltext keyword matching,
    merging results via Reciprocal Rank Fusion (RRF) and expanding context via graph relationships.

    DO NOT call this tool for greetings, pleasantries, small talk, or queries
    unrelated to legal provisions.
    ONLY call this tool when the user asks a substantive question about
    legislation, regulations, articles, recitals, or legal compliance.

    Args:
        query_text: The semantic search query.
        top_k: Number of provisions to retrieve per index before RRF merging (default 15).

    Returns:
        JSON string containing structured RAG context.
    """
    logger.info("Performing hybrid RAG search", query=query_text)
    try:
        embeddings_model = deps.get_embeddings()
        vector = await embeddings_model.aembed_query(query_text)
        driver = await deps.get_neo4j_driver()

        # RRF (Reciprocal Rank Fusion) ranking structures
        rrf_k = 60.0
        rrf_scores: dict[str, float] = {}
        vector_similarities: dict[str, float] = {}
        records_by_id: dict[str, dict[str, Any]] = {}

        def _add_ranked_list(records: list[dict[str, Any]], is_vector: bool = False) -> None:
            for rank, rec in enumerate(records):
                pid = rec.get("provision_id")
                if not pid:
                    continue
                rrf_contrib = 1.0 / (rrf_k + rank + 1.0)
                rrf_scores[pid] = rrf_scores.get(pid, 0.0) + rrf_contrib
                if is_vector:
                    sim = float(rec.get("score", 0.0))
                    vector_similarities[pid] = max(vector_similarities.get(pid, 0.0), sim)
                if pid not in records_by_id:
                    records_by_id[pid] = rec

        async with driver.session() as session:
            # 1. Vector search: Paragraphs
            cypher_para = (
                "CALL db.index.vector.queryNodes('vector_Paragraph', $top_k, $vector) "
                "YIELD node AS p, score "
                "MATCH (a:Article)-[:HAS_PARAGRAPH]->(p) "
                "OPTIONAL MATCH (d:Document)-[:HAS_ARTICLE*]->(a) "
                "OPTIONAL MATCH (c:Chapter)-[:HAS_ARTICLE]->(a) "
                "OPTIONAL MATCH (a)-[:CITES]->(ca:Article) "
                "OPTIONAL MATCH (a)-[:REFERENCES_ANNEX]->(an:Annex) "
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
                "       collect(DISTINCT ca.id) AS cited_articles, "
                "       collect(DISTINCT an.id) AS referenced_annexes "
                "ORDER BY score DESC"
            )
            try:
                result_para = await session.run(cypher_para, {"top_k": top_k, "vector": vector})
                _add_ranked_list([record.data() async for record in result_para], is_vector=True)
            except Exception as pe:
                logger.warning("Paragraph vector search failed", error=str(pe))

            # 2. Vector search: Articles
            cypher_art = (
                "CALL db.index.vector.queryNodes('vector_Article', $top_k, $vector) "
                "YIELD node AS a, score "
                "OPTIONAL MATCH (d:Document)-[:HAS_ARTICLE*]->(a) "
                "OPTIONAL MATCH (c:Chapter)-[:HAS_ARTICLE]->(a) "
                "OPTIONAL MATCH (a)-[:CITES]->(ca:Article) "
                "OPTIONAL MATCH (a)-[:REFERENCES_ANNEX]->(an:Annex) "
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
                "       collect(DISTINCT ca.id) AS cited_articles, "
                "       collect(DISTINCT an.id) AS referenced_annexes "
                "ORDER BY score DESC"
            )
            try:
                result_art = await session.run(cypher_art, {"top_k": top_k, "vector": vector})
                _add_ranked_list([record.data() async for record in result_art], is_vector=True)
            except Exception as ae:
                logger.warning("Article vector search failed", error=str(ae))

            # 3. Vector search: Annexes
            cypher_annex_vec = (
                "CALL db.index.vector.queryNodes('vector_Annex', $top_k, $vector) "
                "YIELD node AS an, score "
                "OPTIONAL MATCH (d:Document)-[:HAS_ANNEX]->(an) "
                "RETURN 'annex' AS type, "
                "       an.id AS paragraph_id, "
                "       an.id AS provision_id, "
                "       an.text AS paragraph_text, "
                "       an.text AS text, "
                "       score, "
                "       an.id AS article_id, "
                "       an.title AS article_title, "
                "       coalesce(d.short_name, d.title, '') AS document, "
                "       '' AS chapter_title, "
                "       [] AS cited_articles, "
                "       [] AS referenced_annexes "
                "ORDER BY score DESC"
            )
            try:
                result_annex_vec = await session.run(cypher_annex_vec, {"top_k": top_k, "vector": vector})
                _add_ranked_list([record.data() async for record in result_annex_vec], is_vector=True)
            except Exception as ave:
                logger.warning("Annex vector search failed", error=str(ave))

            # 4. Vector search: Recitals
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
                "       [] AS cited_articles, "
                "       [] AS referenced_annexes "
                "ORDER BY score DESC"
            )
            try:
                result_rec = await session.run(cypher_rec, {"top_k": top_k, "vector": vector})
                _add_ranked_list([record.data() async for record in result_rec], is_vector=True)
            except Exception as re_err:
                logger.warning("Recital vector search failed", error=str(re_err))

            # 5. Fulltext keyword search: articles
            ft_query = _build_fulltext_query(query_text)
            if ft_query:
                cypher_ft_art = (
                    "CALL db.index.fulltext.queryNodes('article_text', $query) "
                    "YIELD node AS a, score "
                    "OPTIONAL MATCH (d:Document)-[:HAS_ARTICLE*]->(a) "
                    "OPTIONAL MATCH (c:Chapter)-[:HAS_ARTICLE]->(a) "
                    "OPTIONAL MATCH (a)-[:CITES]->(ca:Article) "
                    "OPTIONAL MATCH (a)-[:REFERENCES_ANNEX]->(an:Annex) "
                    "RETURN 'article_ft' AS type, "
                    "       a.id AS paragraph_id, "
                    "       a.id AS provision_id, "
                    "       a.full_text AS paragraph_text, "
                    "       a.full_text AS text, "
                    "       score, "
                    "       a.id AS article_id, "
                    "       a.title AS article_title, "
                    "       coalesce(d.short_name, d.title, '') AS document, "
                    "       coalesce(c.title, '') AS chapter_title, "
                    "       collect(DISTINCT ca.id) AS cited_articles, "
                    "       collect(DISTINCT an.id) AS referenced_annexes "
                    "ORDER BY score DESC "
                    "LIMIT $top_k"
                )
                try:
                    result_ft = await session.run(
                        cypher_ft_art, {"query": ft_query, "top_k": top_k}
                    )
                    _add_ranked_list([record.data() async for record in result_ft], is_vector=False)
                except Exception as ft_err:
                    logger.warning("Fulltext article search failed", error=str(ft_err))

                # 6. Fulltext keyword search: paragraphs
                cypher_ft_para = (
                    "CALL db.index.fulltext.queryNodes('paragraph_text', $query) "
                    "YIELD node AS p, score "
                    "MATCH (a:Article)-[:HAS_PARAGRAPH]->(p) "
                    "OPTIONAL MATCH (d:Document)-[:HAS_ARTICLE*]->(a) "
                    "OPTIONAL MATCH (a)-[:CITES]->(ca:Article) "
                    "OPTIONAL MATCH (a)-[:REFERENCES_ANNEX]->(an:Annex) "
                    "RETURN 'paragraph_ft' AS type, "
                    "       p.id AS paragraph_id, "
                    "       p.id AS provision_id, "
                    "       p.text AS paragraph_text, "
                    "       p.text AS text, "
                    "       score, "
                    "       a.id AS article_id, "
                    "       a.title AS article_title, "
                    "       coalesce(d.short_name, d.title, '') AS document, "
                    "       '' AS chapter_title, "
                    "       collect(DISTINCT ca.id) AS cited_articles, "
                    "       collect(DISTINCT an.id) AS referenced_annexes "
                    "ORDER BY score DESC "
                    "LIMIT $top_k"
                )
                try:
                    result_ft_p = await session.run(
                        cypher_ft_para, {"query": ft_query, "top_k": top_k}
                    )
                    _add_ranked_list([record.data() async for record in result_ft_p], is_vector=False)
                except Exception as ft_p_err:
                    logger.warning("Fulltext paragraph search failed", error=str(ft_p_err))

                # 7. Fulltext keyword search: annexes
                cypher_ft_annex = (
                    "CALL db.index.fulltext.queryNodes('annex_text', $query) "
                    "YIELD node AS an, score "
                    "OPTIONAL MATCH (d:Document)-[:HAS_ANNEX]->(an) "
                    "RETURN 'annex_ft' AS type, "
                    "       an.id AS paragraph_id, "
                    "       an.id AS provision_id, "
                    "       an.text AS paragraph_text, "
                    "       an.text AS text, "
                    "       score, "
                    "       an.id AS article_id, "
                    "       an.title AS article_title, "
                    "       coalesce(d.short_name, d.title, '') AS document, "
                    "       '' AS chapter_title, "
                    "       [] AS cited_articles, "
                    "       [] AS referenced_annexes "
                    "ORDER BY score DESC "
                    "LIMIT $top_k"
                )
                try:
                    result_ft_ann = await session.run(
                        cypher_ft_annex, {"query": ft_query, "top_k": top_k}
                    )
                    _add_ranked_list([record.data() async for record in result_ft_ann], is_vector=False)
                except Exception as ft_ann_err:
                    logger.warning("Fulltext annex search failed", error=str(ft_ann_err))

        # Calculate final RRF blended score and sort
        scored_records: list[dict[str, Any]] = []
        for pid, rec in records_by_id.items():
            base_rrf = rrf_scores.get(pid, 0.0)
            vec_sim = vector_similarities.get(pid, 0.0)
            # Blended score: RRF + 0.3 * vector similarity bonus
            blended_score = round(base_rrf + (0.3 * vec_sim), 4)
            record_copy = dict(rec)
            record_copy["score"] = blended_score
            scored_records.append(record_copy)

        scored_records.sort(key=lambda x: x.get("score", 0.0), reverse=True)
        top_results = scored_records[: max(top_k * 2, 25)]

        logger.info(
            "Hybrid search complete with RRF fusion",
            unique_candidates=len(records_by_id),
            returned=len(top_results),
        )
        return json.dumps({"status": "success", "data": top_results})
    except Exception as e:
        logger.error("Hybrid search failed", error=str(e))
        return json.dumps({"status": "error", "error": str(e)})


def _build_fulltext_query(query_text: str) -> str:
    """Extract key legal and domain terms from query for universal Lucene fulltext search.

    Dynamically extracts quoted phrases, statutory references (Articles, Sections, Annexes),
    classification patterns (e.g. Class IIa, Class III), legal actor roles, and significant terms.
    """
    import re

    ft_terms: list[str] = []
    seen: set[str] = set()

    # 1. Exact phrases in quotes
    for quoted in re.findall(r'"([^"]+)"', query_text):
        q_clean = quoted.strip()
        if q_clean and q_clean.lower() not in seen:
            ft_terms.append(f'"{q_clean}"^3.0')
            seen.add(q_clean.lower())

    # 2. Structural & legal reference patterns across jurisdictions (boosted)
    # e.g. "Article 10", "Art. 20", "Section 4", "Annex XIII", "Chapter II", "Rule 12", "Class III"
    ref_patterns = [
        r"\b(?:article|art\.?)\s+\d+[a-z]?\b",
        r"\b(?:section|sec\.?)\s+\d+[a-z]?\b",
        r"\b(?:annex|schedule|appendix|exhibit)\s+[ivxlcdm0-9]+\b",
        r"\b(?:chapter|title|part)\s+[ivxlcdm0-9]+\b",
        r"\bclass\s+(?:i{1,3}[ab]?|iv|v)\b",
    ]
    for pattern in ref_patterns:
        for match in re.finditer(pattern, query_text, re.IGNORECASE):
            m_text = match.group(0).strip()
            if m_text.lower() not in seen:
                ft_terms.append(f'"{m_text}"^2.5')
                seen.add(m_text.lower())

    # 3. Universal legal qualifiers and operative status phrases (boosted)
    high_priority_qualifiers = [
        "custom-made",
        "investigational",
        "exemption",
        "exempt",
        "exception",
        "shall not apply",
        "does not apply",
        "other than",
        "joint liability",
        "several liability",
        "declaration of conformity",
        "conformity assessment",
    ]
    query_lower = query_text.lower()
    for sq in high_priority_qualifiers:
        if sq in query_lower and sq not in seen:
            ft_terms.append(f'"{sq}"^2.0')
            seen.add(sq)

    general_actors = [
        "notified body",
        "authorised representative",
        "authorized representative",
        "manufacturer",
        "importer",
        "distributor",
        "operator",
        "controller",
        "processor",
    ]
    for ga in general_actors:
        if ga in query_lower and ga not in seen:
            ft_terms.append(f'"{ga}"^1.0')
            seen.add(ga)

    # 4. Significant individual domain tokens (>2 chars, not common stopwords)
    stopwords = {
        "the", "and", "for", "are", "with", "from", "that", "this", "which",
        "what", "does", "how", "who", "when", "where", "about", "their",
        "have", "been", "being", "into", "across", "between", "specific",
        "specifically", "identify", "exact", "requirements", "obligations",
        "under", "such", "some", "more", "also", "each", "will", "would",
        "could", "should", "than", "then", "must", "they", "them", "these",
    }
    clean_words = re.findall(r"\b[A-Za-z0-9_-]{3,}\b", query_text)
    for word in clean_words:
        w_lower = word.lower()
        if w_lower not in stopwords and w_lower not in seen:
            escaped = re.sub(r'([+\-!(){}[\]^"~*?:\\/])', r'\\\1', word)
            ft_terms.append(f"{escaped}^0.8")
            seen.add(w_lower)

    return " OR ".join(ft_terms[:15]) if ft_terms else ""


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
