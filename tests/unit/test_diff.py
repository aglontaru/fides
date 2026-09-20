"""Tests for diff/dedup logic."""

from __future__ import annotations

import json

import pytest

from fides.mcp_server.tools.document_tools import compute_content_hash


@pytest.mark.unit
@pytest.mark.asyncio
async def test_content_hash_computation():
    """Test content hash computation (SHA-256)."""
    res_raw = await compute_content_hash("Test content")
    res = json.loads(res_raw)
    assert res["status"] == "success"
    h = res["hash"]
    assert isinstance(h, str)
    assert len(h) == 64


@pytest.mark.unit
@pytest.mark.asyncio
async def test_identical_documents_same_hash():
    """Test identical documents produce same hash."""
    res1 = json.loads(await compute_content_hash("Doc A"))
    res2 = json.loads(await compute_content_hash("Doc A"))
    assert res1["hash"] == res2["hash"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_modified_documents_different_hash():
    """Test modified documents produce different hash."""
    res1 = json.loads(await compute_content_hash("Doc A"))
    res2 = json.loads(await compute_content_hash("Doc B"))
    assert res1["hash"] != res2["hash"]
