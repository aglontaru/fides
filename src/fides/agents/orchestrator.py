"""Orchestrator Agent implementation using LangChain's DeepAgents framework.

Coordinates autonomous sub-agents (Query, Indexing, Diff, Legal) to handle user intents,
plan ToDo lists, execute tasks, assess quality, and deliver authoritative responses.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import structlog
from deepagents.backends.state import StateBackend
from deepagents.middleware.subagents import SubAgentMiddleware
from langchain.agents import create_agent
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.graph.state import CompiledStateGraph

from fides.agents.contracts import IntentAnalysis, IntentEntities
from fides.agents.prompts import ORCHESTRATOR_SYSTEM_PROMPT
from fides.agents.sub_agents import (
    create_diff_subagent,
    create_graph_builder_subagent,
    create_indexing_subagent,
    create_legal_subagent,
    create_query_subagent,
)
from fides.config.llm import create_agent_model
from fides.config.settings import FidesSettings, get_settings

logger = structlog.get_logger(__name__)

COMMON_GREETINGS = {
    "hi",
    "hello",
    "hey",
    "good morning",
    "good afternoon",
    "good evening",
    "greetings",
    "hi there",
    "hello there",
    "howdy",
    "thanks",
    "thank you",
    "bye",
    "goodbye",
}


def is_simple_greeting(text: str) -> bool:
    """Check whether a text message is a basic greeting that can bypass full legal review."""
    clean = text.strip().lower().rstrip("!.,?")
    words = clean.split()
    return clean in COMMON_GREETINGS or (
        len(words) <= 3 and any(w in words for w in ["hi", "hello", "hey", "greetings"])
    )


def route_intent(text: str) -> IntentAnalysis:
    """Heuristic / rule-based intent classification for fast path decisions."""
    clean = text.strip().lower()
    if is_simple_greeting(clean):
        return IntentAnalysis(
            intent_type="greeting",
            entities=IntentEntities(),
            requires_legal_review=False,
            complexity="simple",
            raw_message=text,
        )

    if any(keyword in clean for keyword in ["upload", "index", "add document", "parse pdf"]):
        return IntentAnalysis(
            intent_type="upload",
            entities=IntentEntities(),
            requires_legal_review=False,
            complexity="simple",
            raw_message=text,
        )

    if any(
        keyword in clean for keyword in ["diff", "compare", "difference", "version", "amendment"]
    ):
        return IntentAnalysis(
            intent_type="diff",
            entities=IntentEntities(),
            requires_legal_review=True,
            complexity="multi_hop",
            raw_message=text,
        )

    return IntentAnalysis(
        intent_type="question",
        entities=IntentEntities(),
        requires_legal_review=True,
        complexity="multi_hop",
        raw_message=text,
    )


async def create_orchestrator(
    settings: FidesSettings | None = None,
    mcp_tools: Sequence[BaseTool] | None = None,
) -> tuple[CompiledStateGraph[Any, Any, Any, Any], Any]:
    """Create and return the autonomous DeepAgent orchestrator with configured sub-agents.

    Args:
        settings: Application settings.
        mcp_tools: Optional pre-loaded MCP tools (e.g. for testing).

    Returns:
        A tuple of (CompiledStateGraph, mcp_client).
    """
    logger.info("Initializing Autonomous DeepAgent Orchestrator")
    s = settings or get_settings()

    # Initialize MCP client with SSE transport
    url = s.mcp_server_url
    if url.endswith("/mcp"):
        url = url[:-4] + "/sse"
    mcp_client = MultiServerMCPClient(
        {
            "fides_tools": {
                "transport": "sse",
                "url": url,
            }
        }
    )

    # Fetch tools from MCP server if not provided
    loaded_tools: list[BaseTool] = list(mcp_tools) if mcp_tools is not None else []
    if not loaded_tools:
        try:
            tools_from_server = await mcp_client.get_tools()
            loaded_tools = list(tools_from_server)
            logger.info("Retrieved tools from MCP server", count=len(loaded_tools))
        except Exception as e:
            logger.warning(
                "Could not fetch tools from MCP server (server might be offline)",
                error=str(e),
                url=s.mcp_server_url,
            )

    # Configure the 5 autonomous sub-agents
    query_sub = create_query_subagent(tools=loaded_tools, settings=s)
    indexing_sub = create_indexing_subagent(tools=loaded_tools, settings=s)
    graph_builder_sub = create_graph_builder_subagent(tools=loaded_tools, settings=s)
    diff_sub = create_diff_subagent(tools=loaded_tools, settings=s)
    legal_sub = create_legal_subagent(settings=s)

    subagents = [query_sub, indexing_sub, graph_builder_sub, diff_sub, legal_sub]

    # Resolve model for orchestrator (allowing per-agent override if configured)
    model = create_agent_model("orchestrator", s)

    # Build SubAgent middleware without filesystem or shell execution tools
    subagent_middleware = SubAgentMiddleware(
        backend=StateBackend(),
        subagents=subagents,
    )

    # Build the Orchestrator with strict recursion limit to prevent infinite loops
    agent = create_agent(
        model=model,
        system_prompt=ORCHESTRATOR_SYSTEM_PROMPT,
        middleware=[subagent_middleware],
        name="orchestrator",
    ).with_config(
        {
            "recursion_limit": 6,
            "metadata": {
                "lc_agent_name": "orchestrator",
            },
        }
    )

    logger.info(
        "Autonomous DeepAgent Orchestrator created successfully",
        subagents=[s["name"] for s in subagents],
    )

    return agent, mcp_client


__all__ = [
    "COMMON_GREETINGS",
    "create_orchestrator",
    "is_simple_greeting",
    "route_intent",
]
