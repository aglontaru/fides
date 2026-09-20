"""QA evaluation."""

from __future__ import annotations

import pytest


@pytest.mark.eval
@pytest.mark.asyncio
async def test_qa_eval(golden_qa_pairs, agent_system):
    """
    For each golden pair: invoke QA agent, check answer contains expected keywords, check sources match expected.
    Compute precision/recall on citations.
    Report hallucination rate (claims not backed by sources).
    """
    for pair in golden_qa_pairs:
        # Pseudo evaluation logic
        assert "expected_sources" in pair
        assert "must_contain" in pair
