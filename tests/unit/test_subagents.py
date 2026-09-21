"""Unit tests for sub-agent definitions and configurations."""

from __future__ import annotations

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.tools import tool

from fides.agents.sub_agents import (
    create_diff_subagent,
    create_indexing_subagent,
    create_legal_subagent,
    create_query_subagent,
    filter_diff_tools,
    filter_indexing_tools,
    filter_query_tools,
)


@tool
def hybrid_search(query: str) -> str:
    """Mock hybrid search tool."""
    return "results"


@tool
def ingest_document(content_base64: str, filename: str) -> str:
    """Mock ingest tool."""
    return "ok"


@tool
def diff_documents(existing_doc_id: str, new_text: str, new_short_name: str) -> str:
    """Mock diff tool."""
    return "diff"


@tool
def unrelated_tool() -> str:
    """Unrelated mock tool."""
    return "none"


@pytest.mark.unit
def test_tool_filtering():
    """Verify tool filtering selects only appropriate tools for each subagent."""
    all_tools = [hybrid_search, ingest_document, diff_documents, unrelated_tool]

    query_tools = filter_query_tools(all_tools)
    assert len(query_tools) == 1
    assert query_tools[0].name == "hybrid_search"

    indexing_tools = filter_indexing_tools(all_tools)
    assert len(indexing_tools) == 1
    assert indexing_tools[0].name == "ingest_document"

    diff_tools = filter_diff_tools(all_tools)
    assert len(diff_tools) == 1
    assert diff_tools[0].name == "diff_documents"


@pytest.mark.unit
def test_subagent_specs():
    """Verify subagent TypedDicts are properly formatted for DeepAgents."""
    fake_llm = FakeListChatModel(responses=["ok"])
    all_tools = [hybrid_search, ingest_document, diff_documents]

    q_sub = create_query_subagent(tools=all_tools, model=fake_llm)
    assert q_sub["name"] == "query"
    assert "hybrid_search" in [t.name for t in q_sub["tools"]]
    assert q_sub["mode"] == "isolated"

    idx_sub = create_indexing_subagent(tools=all_tools, model=fake_llm)
    assert idx_sub["name"] == "indexing"
    assert "ingest_document" in [t.name for t in idx_sub["tools"]]

    diff_sub = create_diff_subagent(tools=all_tools, model=fake_llm)
    assert diff_sub["name"] == "diff"
    assert "diff_documents" in [t.name for t in diff_sub["tools"]]

    legal_sub = create_legal_subagent(model=fake_llm)
    assert legal_sub["name"] == "legal"
    assert len(legal_sub["tools"]) == 0

    from fides.agents.sub_agents import create_graph_builder_subagent
    gb_sub = create_graph_builder_subagent(tools=all_tools, model=fake_llm)
    assert gb_sub["name"] == "graph_builder"
    assert gb_sub["mode"] == "isolated"


@pytest.mark.unit
def test_agent_config_loading():
    """Verify loading agent limits from agents.yaml."""
    from fides.config.agent_config import load_agent_config
    cfg = load_agent_config()
    assert cfg.orchestrator.max_tool_calls > 0
    assert cfg.query.timeout_seconds > 0
    assert cfg.legal.timeout_seconds > 0
    assert cfg.graph_builder.timeout_seconds > 0
    assert cfg.indexing.timeout_seconds > 0
    assert cfg.diff.timeout_seconds > 0
