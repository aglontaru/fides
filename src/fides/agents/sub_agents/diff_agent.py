"""Diff Sub-Agent for legislation change detection and semantic comparison."""

from __future__ import annotations

from collections.abc import Sequence

import structlog
from deepagents.middleware.subagents import SubAgent
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool

from fides.agents.prompts import DIFF_AGENT_SYSTEM_PROMPT
from fides.config.llm import create_agent_model
from fides.config.settings import FidesSettings, get_settings

logger = structlog.get_logger(__name__)

DIFF_TOOL_NAMES = [
    "check_document_exists",
    "diff_documents",
    "diff_articles",
    "neo4j_query",
    "get_article",
    "get_article_with_context",
]

DIFF_AGENT_DESCRIPTION = (
    "Document comparison and change detection specialist. Compares legislation versions at the article "
    "and paragraph level, computing semantic similarity, identifying added, removed, and modified provisions, "
    "and analyzing regulatory impact. Use this agent whenever you need to compare two document versions, "
    "check if a document has changed, or analyze amendments."
)


def filter_diff_tools(tools: Sequence[BaseTool]) -> list[BaseTool]:
    """Filter MCP tools to only those relevant for the Diff Agent."""
    return [t for t in tools if t.name in DIFF_TOOL_NAMES]


def create_diff_subagent(
    tools: Sequence[BaseTool],
    settings: FidesSettings | None = None,
    model: BaseChatModel | str | None = None,
) -> SubAgent:
    """Create a SubAgent specification for the Diff Agent compatible with DeepAgents.

    Args:
        tools: Available MCP tools.
        settings: Application settings.
        model: Optional model override.

    Returns:
        SubAgent TypedDict configuration.
    """
    s = settings or get_settings()
    llm = model or create_agent_model("diff", s)
    agent_tools = filter_diff_tools(tools)

    logger.info("Configuring Diff subagent", tool_count=len(agent_tools))

    return {
        "name": "diff",
        "description": DIFF_AGENT_DESCRIPTION,
        "system_prompt": DIFF_AGENT_SYSTEM_PROMPT,
        "tools": agent_tools,
        "model": llm,
        "mode": "isolated",
    }


__all__ = [
    "DIFF_AGENT_DESCRIPTION",
    "DIFF_TOOL_NAMES",
    "create_diff_subagent",
    "filter_diff_tools",
]
