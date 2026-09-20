"""Indexing evaluation."""

from __future__ import annotations

import pytest


@pytest.mark.eval
@pytest.mark.asyncio
async def test_indexing_eval(agent_system):
    """
    Index a known document, verify all articles/paragraphs captured in graph.
    """
    pass
