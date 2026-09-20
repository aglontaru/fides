"""Dependencies for the FastMCP server tools."""

from __future__ import annotations

import structlog
from langchain_core.embeddings import Embeddings
from neo4j import AsyncDriver, AsyncGraphDatabase

from fides.config.llm import create_embeddings
from fides.config.settings import get_settings

logger = structlog.get_logger(__name__)


class MCPDependencies:
    """Dependency container for MCP tools."""

    def __init__(self) -> None:
        """Initialize dependencies container."""
        self._neo4j_driver: AsyncDriver | None = None
        self._embeddings: Embeddings | None = None
        self._settings = get_settings()

    async def get_neo4j_driver(self) -> AsyncDriver:
        """Get or initialize the Neo4j async driver."""
        if self._neo4j_driver is None:
            logger.info("Initializing Neo4j driver")
            self._neo4j_driver = AsyncGraphDatabase.driver(
                self._settings.neo4j_uri,
                auth=(
                    self._settings.neo4j_user,
                    self._settings.neo4j_password.get_secret_value(),
                ),
            )
            # Verify connectivity
            await self._neo4j_driver.verify_connectivity()
        return self._neo4j_driver

    def get_embeddings(self) -> Embeddings:
        """Get or initialize the embeddings model using provider factory."""
        if self._embeddings is None:
            logger.info("Initializing embeddings model")
            self._embeddings = create_embeddings(self._settings)
        return self._embeddings

    async def close(self) -> None:
        """Close all connections."""
        if self._neo4j_driver is not None:
            logger.info("Closing Neo4j driver")
            await self._neo4j_driver.close()
            self._neo4j_driver = None


deps = MCPDependencies()
