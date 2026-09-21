"""Query Sub-Agent for autonomous regulatory retrieval."""

from __future__ import annotations

from collections.abc import Sequence

import structlog
from deepagents.middleware.subagents import SubAgent
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool

from fides.agents.prompts import QUERY_AGENT_SYSTEM_PROMPT
from fides.config.llm import create_agent_model
from fides.config.settings import FidesSettings, get_settings

logger = structlog.get_logger(__name__)

QUERY_TOOL_NAMES = [
    "hybrid_search",
    "vector_search",
    "neo4j_query",
    "get_graph_schema",
    "get_provision",
    "get_article",
    "get_article_with_context",
    "find_document",
    "get_graph_stats",
]

QUERY_AGENT_DESCRIPTION = (
    "Expert legal information retrieval specialist. Decomposes complex queries into focused "
    "sub-queries (including exemptions and derogations), runs hybrid vector + keyword search, "
    "retrieves article context with cross-references and defined terms from Neo4j, and self-assesses "
    "retrieval coverage. Use this agent whenever you need to search or retrieve legislative provisions, "
    "articles, recitals, or definitions from the knowledge graph."
)


def filter_query_tools(tools: Sequence[BaseTool]) -> list[BaseTool]:
    """Filter MCP tools to only those relevant for the Query Agent."""
    return [t for t in tools if t.name in QUERY_TOOL_NAMES]


def create_query_subagent(
    tools: Sequence[BaseTool],
    settings: FidesSettings | None = None,
    model: BaseChatModel | str | None = None,
) -> SubAgent:
    """Create a SubAgent specification for the Query Agent compatible with DeepAgents.

    Args:
        tools: Available MCP tools.
        settings: Application settings.
        model: Optional model override.

    Returns:
        SubAgent TypedDict configuration.
    """
    s = settings or get_settings()
    llm = model or create_agent_model("query", s)
    agent_tools = filter_query_tools(tools)

    logger.info("Configuring Query subagent", tool_count=len(agent_tools))

    return {
        "name": "query",
        "description": QUERY_AGENT_DESCRIPTION,
        "system_prompt": QUERY_AGENT_SYSTEM_PROMPT,
        "tools": agent_tools,
        "model": llm,
        "mode": "isolated",
    }


__all__ = [
    "QUERY_AGENT_DESCRIPTION",
    "QUERY_TOOL_NAMES",
    "create_query_subagent",
    "filter_query_tools",
]
