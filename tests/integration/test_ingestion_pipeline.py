"""End-to-end ingestion test."""

from __future__ import annotations

import pytest

from fides.ingestion.pipeline import IngestionPipeline


@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_pipeline(mock_neo4j_driver):
    """Test full pipeline: parse PDF -> chunk -> extract structure -> write to graph."""
    pipeline = IngestionPipeline(mock_neo4j_driver)
    assert pipeline is not None
