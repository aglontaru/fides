"""Neo4j graph interaction tools."""

from __future__ import annotations

import json
from typing import Any

import structlog

from fides.mcp_server.dependencies import deps
from fides.mcp_server.server import mcp

logger = structlog.get_logger(__name__)


@mcp.tool()
async def neo4j_query(cypher: str, parameters: dict[str, Any] | None = None) -> str:
    """Execute a read-only Cypher query and return JSON results."""
    logger.info("Executing Neo4j read query", cypher=cypher)
    try:
        driver = await deps.get_neo4j_driver()
        async with driver.session() as session:
            result = await session.run(cypher, parameters or {})
            records = [record.data() async for record in result]
            return json.dumps({"status": "success", "data": records})
    except Exception as e:
        logger.error("Error executing Neo4j read query", error=str(e))
        return json.dumps({"status": "error", "error": str(e)})


@mcp.tool()
async def neo4j_write(cypher: str, parameters: dict[str, Any] | None = None) -> str:
    """Execute a write Cypher query."""
    logger.info("Executing Neo4j write query", cypher=cypher)
    try:
        driver = await deps.get_neo4j_driver()
        async with driver.session() as session:
            result = await session.run(cypher, parameters or {})
            summary = await result.consume()
            counters = summary.counters
            return json.dumps(
                {
                    "status": "success",
                    "updates": {
                        "nodes_created": counters.nodes_created,
                        "nodes_deleted": counters.nodes_deleted,
                        "relationships_created": counters.relationships_created,
                        "relationships_deleted": counters.relationships_deleted,
                        "properties_set": counters.properties_set,
                    },
                }
            )
    except Exception as e:
        logger.error("Error executing Neo4j write query", error=str(e))
        return json.dumps({"status": "error", "error": str(e)})


@mcp.tool()
async def find_document(title: str | None = None, short_name: str | None = None) -> str:
    """Find a document in the graph by title or short_name."""
    if not title and not short_name:
        return json.dumps({"status": "error", "error": "Must provide either title or short_name"})

    cypher = (
        "MATCH (d:Document) "
        "WHERE ($title IS NULL OR d.title CONTAINS $title) "
        "  AND ($short_name IS NULL OR d.short_name = $short_name) "
        "RETURN d.id AS id, d.title AS title, d.short_name AS short_name, d.content_hash AS content_hash"
    )
    res = await neo4j_query(cypher, {"title": title, "short_name": short_name})
    return str(res)


@mcp.tool()
async def get_article(article_id: str) -> str:
    """Get an article by ID with its full text."""
    cypher = (
        "MATCH (a:Article {id: $article_id}) "
        "OPTIONAL MATCH (a)-[:HAS_PARAGRAPH]->(p:Paragraph) "
        "RETURN a.id AS article_id, a.title AS title, "
        "       coalesce(a.full_text, a.text) AS full_text, "
        "       collect(p.text) AS paragraphs"
    )
    res = await neo4j_query(cypher, {"article_id": article_id})
    return str(res)


@mcp.tool()
async def get_article_with_context(article_id: str) -> str:
    """Get an article with its parent chapter, referenced recitals, cross-refs, and definitions used."""
    cypher = (
        "MATCH (a:Article {id: $article_id}) "
        "OPTIONAL MATCH (c:Chapter)-[:HAS_ARTICLE]->(a) "
        "OPTIONAL MATCH (a)-[:INTERPRETED_BY]->(r:Recital) "
        "OPTIONAL MATCH (a)-[:CITES]->(ca:Article) "
        "OPTIONAL MATCH (a)-[:USES_TERM]->(dt:DefinedTerm) "
        "RETURN a.id AS article_id, "
        "       a.text AS article_text, "
        "       c.title AS chapter_title, "
        "       collect(DISTINCT r.text) AS recitals, "
        "       collect(DISTINCT ca.id) AS cited_articles, "
        "       collect(DISTINCT dt.term + ': ' + dt.definition) AS defined_terms"
    )
    res = await neo4j_query(cypher, {"article_id": article_id})
    return str(res)


@mcp.tool()
async def get_graph_stats() -> str:
    """Get node and edge counts by type in the knowledge graph."""
    cypher_nodes = "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count"
    cypher_edges = "MATCH ()-[r]->() RETURN type(r) AS type, count(r) AS count"

    try:
        driver = await deps.get_neo4j_driver()
        async with driver.session() as session:
            nodes_res = await session.run(cypher_nodes)
            nodes = [record.data() async for record in nodes_res]
            edges_res = await session.run(cypher_edges)
            edges = [record.data() async for record in edges_res]

            return json.dumps({"status": "success", "data": {"nodes": nodes, "edges": edges}})
    except Exception as e:
        logger.error("Error fetching graph stats", error=str(e))
        return json.dumps({"status": "error", "error": str(e)})
