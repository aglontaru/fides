"""
Cypher schema initialization for the Fides knowledge graph.
"""

from __future__ import annotations

import structlog
from neo4j import AsyncDriver

logger = structlog.get_logger(__name__)


def get_schema_statements(embedding_dimensions: int = 768) -> list[str]:
    """
    Get Cypher statements to initialize the database schema.
    Includes constraints and indexes.
    """
    return [
        # Constraints
        "CREATE CONSTRAINT document_id IF NOT EXISTS FOR (n:Document) REQUIRE n.id IS UNIQUE;",
        "CREATE CONSTRAINT recital_id IF NOT EXISTS FOR (n:Recital) REQUIRE n.id IS UNIQUE;",
        "CREATE CONSTRAINT chapter_id IF NOT EXISTS FOR (n:Chapter) REQUIRE n.id IS UNIQUE;",
        "CREATE CONSTRAINT section_id IF NOT EXISTS FOR (n:Section) REQUIRE n.id IS UNIQUE;",
        "CREATE CONSTRAINT article_id IF NOT EXISTS FOR (n:Article) REQUIRE n.id IS UNIQUE;",
        "CREATE CONSTRAINT paragraph_id IF NOT EXISTS FOR (n:Paragraph) REQUIRE n.id IS UNIQUE;",
        "CREATE CONSTRAINT annex_id IF NOT EXISTS FOR (n:Annex) REQUIRE n.id IS UNIQUE;",
        "CREATE CONSTRAINT term_id IF NOT EXISTS FOR (n:DefinedTerm) REQUIRE n.id IS UNIQUE;",
        "CREATE CONSTRAINT obligation_id IF NOT EXISTS FOR (n:Obligation) REQUIRE n.id IS UNIQUE;",
        "CREATE CONSTRAINT actor_role_id IF NOT EXISTS FOR (n:ActorRole) REQUIRE n.id IS UNIQUE;",
        # Additional property indexes for faster lookups
        "CREATE INDEX document_hash IF NOT EXISTS FOR (n:Document) ON (n.content_hash);",
        "CREATE INDEX document_short_name IF NOT EXISTS FOR (n:Document) ON (n.short_name);",
        # Fulltext Indexes
        """
        CREATE FULLTEXT INDEX article_text IF NOT EXISTS
        FOR (n:Article) ON EACH [n.title, n.full_text];
        """,
        """
        CREATE FULLTEXT INDEX paragraph_text IF NOT EXISTS
        FOR (n:Paragraph) ON EACH [n.text];
        """,
        """
        CREATE FULLTEXT INDEX recital_text IF NOT EXISTS
        FOR (n:Recital) ON EACH [n.text];
        """,
        # Vector Indexes
        f"""
        CREATE VECTOR INDEX vector_Article IF NOT EXISTS
        FOR (n:Article) ON (n.embedding)
        OPTIONS {{indexConfig: {{
            `vector.dimensions`: {embedding_dimensions},
            `vector.similarity_function`: 'cosine'
        }}}};
        """,
        f"""
        CREATE VECTOR INDEX vector_Paragraph IF NOT EXISTS
        FOR (n:Paragraph) ON (n.embedding)
        OPTIONS {{indexConfig: {{
            `vector.dimensions`: {embedding_dimensions},
            `vector.similarity_function`: 'cosine'
        }}}};
        """,
        f"""
        CREATE VECTOR INDEX vector_Recital IF NOT EXISTS
        FOR (n:Recital) ON (n.embedding)
        OPTIONS {{indexConfig: {{
            `vector.dimensions`: {embedding_dimensions},
            `vector.similarity_function`: 'cosine'
        }}}};
        """,
        f"""
        CREATE VECTOR INDEX vector_Annex IF NOT EXISTS
        FOR (n:Annex) ON (n.embedding)
        OPTIONS {{indexConfig: {{
            `vector.dimensions`: {embedding_dimensions},
            `vector.similarity_function`: 'cosine'
        }}}};
        """,
    ]


async def initialize_schema(driver: AsyncDriver, embedding_dimensions: int = 768) -> None:
    """
    Execute all schema initialization statements.
    """
    logger.info("Initializing Neo4j schema", embedding_dimensions=embedding_dimensions)
    statements = get_schema_statements(embedding_dimensions)

    async with driver.session() as session:
        for stmt in statements:
            try:
                await session.run(stmt)
                logger.debug("Executed schema statement", statement=stmt.strip())
            except Exception as e:
                logger.error("Failed to execute schema statement", statement=stmt, error=str(e))
                raise
