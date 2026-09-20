"""Eval-specific fixtures."""

from __future__ import annotations

import json
import os

import pytest

from fides.agents.factory import create_agent_system


@pytest.fixture
def golden_qa_pairs():
    """loads from qa_golden.jsonl"""
    path = os.path.join(os.path.dirname(__file__), "datasets", "qa_golden.jsonl")
    pairs = []
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                pairs.append(json.loads(line.strip()))
    return pairs


@pytest.fixture
def agent_system():
    """creates a real AgentSystem for eval"""
    return create_agent_system()
