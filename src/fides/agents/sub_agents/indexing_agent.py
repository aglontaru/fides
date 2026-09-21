"""Indexing Sub-Agent for document parsing, chunking, and knowledge graph ingestion."""

from __future__ import annotations

from collections.abc import Sequence

import structlog
from deepagents.middleware.subagents import SubAgent
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool

from fides.agents.prompts import INDEXING_AGENT_SYSTEM_PROMPT
from fides.config.llm import create_agent_model
from fides.config.settings import FidesSettings, get_settings

logger = structlog.get_logger(__name__)

INDEXING_TOOL_NAMES = [
    "ingest_document",
    "parse_document",
    "chunk_legislation",
    "extract_structure",
    "compute_content_hash",
    "check_document_exists",
    "neo4j_write",
    "neo4j_query",
    "vector_upsert",
]

INDEXING_AGENT_DESCRIPTION = (
    "Document ingestion and knowledge graph maintenance specialist. Handles document parsing, "
    "hierarchical legislation chunking, deduplication checks, vector embeddings, dynamic ontology "
    "discovery, and Neo4j graph storage. Also handles document subgraph deletion. "
    "Use this agent whenever a document needs to be uploaded, indexed, or deleted."
)


def filter_indexing_tools(tools: Sequence[BaseTool]) -> list[BaseTool]:
    """Filter MCP tools to only those relevant for the Indexing Agent."""
    return [t for t in tools if t.name in INDEXING_TOOL_NAMES]


def create_indexing_subagent(
    tools: Sequence[BaseTool],
    settings: FidesSettings | None = None,
    model: BaseChatModel | str | None = None,
) -> SubAgent:
    """Create a SubAgent specification for the Indexing Agent compatible with DeepAgents.

    Args:
        tools: Available MCP tools.
        settings: Application settings.
        model: Optional model override.

    Returns:
        SubAgent TypedDict configuration.
    """
    s = settings or get_settings()
    llm = model or create_agent_model("indexing", s)
    agent_tools = filter_indexing_tools(tools)

    logger.info("Configuring Indexing subagent", tool_count=len(agent_tools))

    return {
        "name": "indexing",
        "description": INDEXING_AGENT_DESCRIPTION,
        "system_prompt": INDEXING_AGENT_SYSTEM_PROMPT,
        "tools": agent_tools,
        "model": llm,
        "mode": "isolated",
    }


__all__ = [
    "INDEXING_AGENT_DESCRIPTION",
    "INDEXING_TOOL_NAMES",
    "create_indexing_subagent",
    "filter_indexing_tools",
]
