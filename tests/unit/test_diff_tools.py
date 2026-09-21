"""Unit tests for diff tools and semantic similarity."""

from __future__ import annotations

import pytest

from fides.mcp_server.tools.diff_tools import _cosine_similarity


@pytest.mark.unit
def test_cosine_similarity_identical():
    """Identical vectors should have similarity of 1.0."""
    v1 = [1.0, 2.0, 3.0]
    v2 = [1.0, 2.0, 3.0]
    sim = _cosine_similarity(v1, v2)
    assert pytest.approx(sim, 0.0001) == 1.0


@pytest.mark.unit
def test_cosine_similarity_orthogonal():
    """Orthogonal vectors should have similarity of 0.0."""
    v1 = [1.0, 0.0]
    v2 = [0.0, 1.0]
    sim = _cosine_similarity(v1, v2)
    assert pytest.approx(sim, 0.0001) == 0.0


@pytest.mark.unit
def test_cosine_similarity_opposite():
    """Opposite vectors should have similarity of -1.0."""
    v1 = [1.0, 2.0]
    v2 = [-1.0, -2.0]
    sim = _cosine_similarity(v1, v2)
    assert pytest.approx(sim, 0.0001) == -1.0


@pytest.mark.unit
def test_cosine_similarity_zero_vector():
    """Zero vectors should return 0.0 without divide-by-zero error."""
    v1 = [0.0, 0.0]
    v2 = [1.0, 2.0]
    sim = _cosine_similarity(v1, v2)
    assert sim == 0.0
