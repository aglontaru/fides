"""Graph Builder Sub-Agent for dynamic ontology discovery and knowledge graph expansion."""

from __future__ import annotations

from collections.abc import Sequence

import structlog
from deepagents.middleware.subagents import SubAgent
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool

from fides.agents.prompts import GRAPH_BUILDER_AGENT_SYSTEM_PROMPT
from fides.config.llm import create_agent_model
from fides.config.settings import FidesSettings, get_settings

logger = structlog.get_logger(__name__)

GRAPH_BUILDER_TOOL_NAMES = [
    "get_graph_schema",
    "neo4j_write",
    "neo4j_query",
    "vector_upsert",
    "get_provision",
    "get_article",
    "get_article_with_context",
    "get_graph_stats",
]

GRAPH_BUILDER_AGENT_DESCRIPTION = (
    "Dynamic ontology and knowledge graph builder. Analyzes legal provisions to discover "
    "domain taxonomies, new Node types (actors, defined terms, normative rules, domain concepts) "
    "and new Relationship types, and dynamically adds them into the Neo4j knowledge graph. "
    "Use this agent whenever new legal entities, concepts, or semantic relationships need to be "
    "discovered or added to the knowledge graph."
)


def filter_graph_builder_tools(tools: Sequence[BaseTool]) -> list[BaseTool]:
    """Filter MCP tools to only those relevant for the Graph Builder Agent."""
    return [t for t in tools if t.name in GRAPH_BUILDER_TOOL_NAMES]


def create_graph_builder_subagent(
    tools: Sequence[BaseTool],
    settings: FidesSettings | None = None,
    model: BaseChatModel | str | None = None,
) -> SubAgent:
    """Create a SubAgent specification for the Dynamic Graph Builder Agent.

    Args:
        tools: Available MCP tools.
        settings: Application settings.
        model: Optional model override.

    Returns:
        SubAgent TypedDict configuration.
    """
    s = settings or get_settings()
    llm = model or create_agent_model("graph_builder", s)
    agent_tools = filter_graph_builder_tools(tools)

    logger.info("Configuring Graph Builder subagent", tool_count=len(agent_tools))

    return {
        "name": "graph_builder",
        "description": GRAPH_BUILDER_AGENT_DESCRIPTION,
        "system_prompt": GRAPH_BUILDER_AGENT_SYSTEM_PROMPT,
        "tools": agent_tools,
        "model": llm,
        "mode": "isolated",
    }


__all__ = [
    "GRAPH_BUILDER_AGENT_DESCRIPTION",
    "GRAPH_BUILDER_TOOL_NAMES",
    "create_graph_builder_subagent",
    "filter_graph_builder_tools",
]
