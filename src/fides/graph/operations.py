"""
Graph CRUD operations using the Neo4j async driver.
"""

from __future__ import annotations

from typing import Any

import structlog
from neo4j import AsyncDriver, AsyncManagedTransaction
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .models import (
    ArticleNode,
    DocumentNode,
    ParagraphNode,
    RecitalNode,
    RelType,
)

logger = structlog.get_logger(__name__)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
async def upsert_document(driver: AsyncDriver, doc: DocumentNode) -> None:
    """Upsert a DocumentNode."""
    async with driver.session() as session:

        async def _tx_func(tx: AsyncManagedTransaction, /) -> None:
            query = """
            MERGE (d:Document {id: $props.id})
            SET d += $props
            """
            await tx.run(query, props=doc.to_neo4j_properties())

        await session.execute_write(_tx_func)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
async def upsert_article(driver: AsyncDriver, doc_id: str, article: ArticleNode) -> None:
    """Upsert an ArticleNode and link it to the Document."""
    async with driver.session() as session:

        async def _tx_func(tx: AsyncManagedTransaction, /) -> None:
            query = """
            MATCH (d:Document {id: $doc_id})
            MERGE (a:Article {id: $props.id})
            SET a += $props
            MERGE (d)-[:HAS_ARTICLE]->(a)
            """
            await tx.run(query, doc_id=doc_id, props=article.to_neo4j_properties())

        await session.execute_write(_tx_func)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
async def upsert_paragraph(driver: AsyncDriver, article_id: str, para: ParagraphNode) -> None:
    """Upsert a ParagraphNode and link it to the Article."""
    async with driver.session() as session:

        async def _tx_func(tx: AsyncManagedTransaction, /) -> None:
            query = """
            MATCH (a:Article {id: $article_id})
            MERGE (p:Paragraph {id: $props.id})
            SET p += $props
            MERGE (a)-[:HAS_PARAGRAPH]->(p)
            """
            await tx.run(query, article_id=article_id, props=para.to_neo4j_properties())

        await session.execute_write(_tx_func)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
async def upsert_recital(driver: AsyncDriver, doc_id: str, recital: RecitalNode) -> None:
    """Upsert a RecitalNode and link it to the Document."""
    async with driver.session() as session:

        async def _tx_func(tx: AsyncManagedTransaction, /) -> None:
            query = """
            MATCH (d:Document {id: $doc_id})
            MERGE (r:Recital {id: $props.id})
            SET r += $props
            MERGE (d)-[:HAS_RECITAL]->(r)
            """
            await tx.run(query, doc_id=doc_id, props=recital.to_neo4j_properties())

        await session.execute_write(_tx_func)


async def find_document_by_hash(driver: AsyncDriver, content_hash: str) -> DocumentNode | None:
    """Find a Document by its content hash."""
    async with driver.session() as session:

        async def _tx_func(tx: AsyncManagedTransaction, /) -> dict[str, Any] | None:
            query = "MATCH (d:Document {content_hash: $content_hash}) RETURN d"
            result = await tx.run(query, content_hash=content_hash)
            record = await result.single()
            return dict(record["d"]) if record else None

        props = await session.execute_read(_tx_func)
        return DocumentNode(**props) if props else None


async def find_document_by_name(driver: AsyncDriver, short_name: str) -> DocumentNode | None:
    """Find a Document by its short name."""
    async with driver.session() as session:

        async def _tx_func(tx: AsyncManagedTransaction, /) -> dict[str, Any] | None:
            query = "MATCH (d:Document {short_name: $short_name}) RETURN d"
            result = await tx.run(query, short_name=short_name)
            record = await result.single()
            return dict(record["d"]) if record else None

        props = await session.execute_read(_tx_func)
        return DocumentNode(**props) if props else None


async def get_article(driver: AsyncDriver, article_id: str) -> ArticleNode | None:
    """Get an article by ID."""
    async with driver.session() as session:

        async def _tx_func(tx: AsyncManagedTransaction, /) -> dict[str, Any] | None:
            query = "MATCH (a:Article {id: $article_id}) RETURN a"
            result = await tx.run(query, article_id=article_id)
            record = await result.single()
            return dict(record["a"]) if record else None

        props = await session.execute_read(_tx_func)
        return ArticleNode(**props) if props else None


async def get_article_with_context(driver: AsyncDriver, article_id: str) -> dict[str, Any]:
    """Get article with its parent chapter, recitals, and cross-references."""
    async with driver.session() as session:

        async def _tx_func(tx: AsyncManagedTransaction, /) -> dict[str, Any]:
            query = """
            MATCH (a:Article {id: $article_id})
            OPTIONAL MATCH (c:Chapter)-[:HAS_ARTICLE|CONTAINS*]->(a)
            OPTIONAL MATCH (a)-[:INTERPRETED_BY]->(r:Recital)
            OPTIONAL MATCH (a)-[:CITES]->(ref:Article)
            RETURN
                a AS article,
                c AS chapter,
                collect(DISTINCT r) AS recitals,
                collect(DISTINCT ref) AS cross_references
            """
            result = await tx.run(query, article_id=article_id)
            record = await result.single()

            if not record:
                return {}

            return {
                "article": dict(record["article"]) if record["article"] else None,
                "chapter": dict(record["chapter"]) if record["chapter"] else None,
                "recitals": [dict(r) for r in record["recitals"] if r],
                "cross_references": [dict(ref) for ref in record["cross_references"] if ref],
            }

        return await session.execute_read(_tx_func)


async def get_document_articles(driver: AsyncDriver, doc_id: str) -> list[ArticleNode]:
    """Get all articles for a document."""
    async with driver.session() as session:

        async def _tx_func(tx: AsyncManagedTransaction, /) -> list[dict[str, Any]]:
            query = """
            MATCH (d:Document {id: $doc_id})-[:HAS_ARTICLE|CONTAINS*]->(a:Article)
            RETURN a
            ORDER BY a.number
            """
            result = await tx.run(query, doc_id=doc_id)
            return [dict(record["a"]) async for record in result]

        records = await session.execute_read(_tx_func)
        return [ArticleNode(**r) for r in records]


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
async def create_cross_reference(
    driver: AsyncDriver, from_id: str, to_id: str, ref_type: str = RelType.CITES.value
) -> None:
    """Create a cross-reference relationship between two nodes."""
    async with driver.session() as session:

        async def _tx_func(tx: AsyncManagedTransaction, /) -> None:
            # We use dynamic relationship types here, which is fine as ref_type is controlled
            query = f"""
            MATCH (a {{id: $from_id}})
            MATCH (b {{id: $to_id}})
            MERGE (a)-[:{ref_type}]->(b)
            """
            await tx.run(query, from_id=from_id, to_id=to_id)

        await session.execute_write(_tx_func)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
async def delete_document_graph(driver: AsyncDriver, doc_id: str) -> int:
    """Delete a document and all nodes in its subgraph by id or short_name."""
    async with driver.session() as session:

        async def _tx_func(tx: AsyncManagedTransaction, /) -> int:
            query = """
            MATCH (d:Document)
            WHERE d.id = $doc_id OR d.short_name = $doc_id OR d.id = ('doc:' + $doc_id)
            OPTIONAL MATCH (d)-[*]->(n)
            WITH d, collect(DISTINCT n) AS descendants
            UNWIND (descendants + d) AS node
            WITH DISTINCT node
            DETACH DELETE node
            RETURN count(node) AS deleted_count
            """
            result = await tx.run(query, doc_id=doc_id)
            record = await result.single()
            return int(record["deleted_count"]) if record else 0

        return await session.execute_write(_tx_func)


async def get_graph_stats(driver: AsyncDriver) -> dict[str, Any]:
    """Get node and relationship counts."""
    async with driver.session() as session:

        async def _tx_func(tx: AsyncManagedTransaction, /) -> dict[str, Any]:
            # Get node counts by label
            nodes_query = """
            MATCH (n)
            RETURN labels(n)[0] AS label, count(n) AS count
            """
            nodes_result = await tx.run(nodes_query)
            node_counts = {
                record["label"]: record["count"] async for record in nodes_result if record["label"]
            }

            # Get relationship counts by type
            rels_query = """
            MATCH ()-[r]->()
            RETURN type(r) AS type, count(r) AS count
            """
            rels_result = await tx.run(rels_query)
            rel_counts = {
                record["type"]: record["count"] async for record in rels_result if record["type"]
            }

            return {
                "nodes": node_counts,
                "relationships": rel_counts,
                "total_nodes": sum(node_counts.values()),
                "total_relationships": sum(rel_counts.values()),
            }

        return await session.execute_read(_tx_func)


async def get_document_chunks_manifest(driver: AsyncDriver, doc_id: str) -> dict[str, Any]:
    """Retrieve existing article, paragraph, and recital hashes for a document."""
    async with driver.session() as session:

        async def _tx_func(tx: AsyncManagedTransaction, /) -> dict[str, Any]:
            query = """
            MATCH (d:Document {id: $doc_id})
            OPTIONAL MATCH (d)-[:HAS_ARTICLE]->(a:Article)
            OPTIONAL MATCH (a)-[:HAS_PARAGRAPH]->(p:Paragraph)
            OPTIONAL MATCH (d)-[:HAS_RECITAL]->(r:Recital)
            RETURN
                collect(DISTINCT {id: a.id, hash: a.content_hash}) AS articles,
                collect(DISTINCT {id: p.id, hash: p.content_hash}) AS paragraphs,
                collect(DISTINCT {id: r.id, text: r.text}) AS recitals
            """
            result = await tx.run(query, doc_id=doc_id)
            record = await result.single()
            if not record:
                return {"articles": {}, "paragraphs": {}, "recitals": {}}

            articles = {
                item["id"]: item["hash"]
                for item in record["articles"]
                if item and item.get("id")
            }
            paragraphs = {
                item["id"]: item["hash"]
                for item in record["paragraphs"]
                if item and item.get("id")
            }
            recitals = {
                item["id"]: item["text"]
                for item in record["recitals"]
                if item and item.get("id")
            }
            return {
                "articles": articles,
                "paragraphs": paragraphs,
                "recitals": recitals,
            }

        return await session.execute_read(_tx_func)
