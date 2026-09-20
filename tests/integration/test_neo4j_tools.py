"""Integration tests for Neo4j graph operations."""

from __future__ import annotations

import pytest

from fides.graph.schema import initialize_schema


@pytest.mark.integration
@pytest.mark.asyncio
async def test_graph_schema_initialization(mock_neo4j_driver):
    """Test graph schema initialization."""
    await initialize_schema(mock_neo4j_driver)
    mock_neo4j_driver.session.assert_called()
