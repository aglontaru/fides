"""Orchestrator LangGraph agent setup."""

from __future__ import annotations

import json
from typing import Annotated, Any, TypedDict

import structlog
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from fides.agents.prompts import (
    GREETING_SYSTEM_PROMPT,
    LEGAL_SYNTHESIS_SYSTEM_PROMPT,
    LEGAL_SYNTHESIS_USER_INSTRUCTIONS,
    QUERY_DECOMPOSITION_PROMPT,
)
from fides.config import create_chat_model
from fides.config.settings import FidesSettings
from fides.mcp_server.tools.vector_tools import hybrid_search

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


class FidesState(TypedDict):
    """LangGraph state schema for Fides agent."""

    messages: Annotated[list[BaseMessage], add_messages]
    retrieved_context: str


def route_intent(state: FidesState) -> str:
    """Classify user intent into greeting or regulatory retrieval."""
    if not state.get("messages"):
        return "greeting_node"
    last_msg = state["messages"][-1]
    content = getattr(last_msg, "content", "")
    if isinstance(content, list):
        text = " ".join(str(p) for p in content)
    else:
        text = str(content)
    clean = text.strip().lower().rstrip("!.,?")
    words = clean.split()

    if clean in COMMON_GREETINGS or (
        len(words) <= 3 and any(w in words for w in ["hi", "hello", "hey"])
    ):
        return "greeting_node"
    return "retrieve_node"


async def greeting_node(state: FidesState) -> dict[str, Any]:
    """Provide a direct, warm greeting explaining Fides capabilities."""
    llm = create_chat_model()
    prompt = [
        SystemMessage(content=GREETING_SYSTEM_PROMPT),
        *state["messages"],
    ]
    res = await llm.ainvoke(prompt)
    return {"messages": [res]}


async def retrieve_node(state: FidesState) -> dict[str, Any]:
    """Decompose the query and perform multi-index hybrid retrieval from Neo4j."""
    llm = create_chat_model()
    user_query = ""
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, HumanMessage):
            user_query = str(msg.content)
            break

    if not user_query:
        return {"retrieved_context": ""}

    # 1. Query decomposition for broad legal coverage
    decomp_prompt = f"{QUERY_DECOMPOSITION_PROMPT}\n\nQuestion: {user_query}"
    sub_queries = [user_query]
    try:
        raw_res = await llm.ainvoke([SystemMessage(content=decomp_prompt)])
        raw_text = getattr(raw_res, "content", "")
        if "[" in raw_text and "]" in raw_text:
            parsed = json.loads(raw_text[raw_text.find("[") : raw_text.rfind("]") + 1])
            if isinstance(parsed, list):
                sub_queries.extend([str(q) for q in parsed if str(q).strip()])
    except Exception as e:
        logger.debug(f"Decomposition fallback: {e}")

    # 2. Multi-pass search across sub-queries
    all_provisions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for sq in sub_queries[:6]:
        try:
            search_res = await hybrid_search(sq, top_k=6)
            data = json.loads(search_res).get("data", [])
            for p in data:
                pid = p.get("provision_id")
                if pid and pid not in seen:
                    seen.add(pid)
                    all_provisions.append(p)
        except Exception as se:
            logger.warning(f"Retrieval error for sub-query: {se}", query=sq)

    all_provisions.sort(key=lambda x: x.get("score", 0.0), reverse=True)

    # 3. Format provisions with accurate citation labels
    blocks: list[str] = []
    for p in all_provisions[:14]:
        doc = p.get("document", "")
        art_id = p.get("article_id", "")
        art_num = art_id.rsplit(":", 1)[-1] if ":" in art_id else art_id
        para_id = p.get("paragraph_id", "")
        para_num = para_id.rsplit(":", 1)[-1] if ":para:" in para_id else ""

        if art_num == "168" and para_num:
            ref = f"[{doc}, Recital ({para_num})]"
        else:
            ref = f"[{doc}, Art. {art_num}]"
            if para_num and para_num != art_num:
                ref = f"[{doc}, Art. {art_num}, Para. {para_num}]"

        txt = (p.get("text") or p.get("paragraph_text", "")).strip()[:1000]
        if txt:
            blocks.append(f"{ref}\n{txt}")

    return {"retrieved_context": "\n\n---\n\n".join(blocks)}


async def synthesize_node(state: FidesState) -> dict[str, Any]:
    """Synthesize high-level, authoritative legal analysis grounded strictly in provisions."""
    llm = create_chat_model()
    user_query = ""
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, HumanMessage):
            user_query = str(msg.content)
            break

    context = state.get("retrieved_context", "")

    user_prompt = (
        f"Authoritative Provisions from Knowledge Graph:\n\n{context}\n\n"
        f"---\n\nUser Question:\n{user_query}\n\n"
        f"{LEGAL_SYNTHESIS_USER_INSTRUCTIONS}"
    )

    res = await llm.ainvoke(
        [
            SystemMessage(content=LEGAL_SYNTHESIS_SYSTEM_PROMPT),
            *state["messages"][:-1],
            HumanMessage(content=user_prompt),
        ]
    )
    return {"messages": [res]}


async def create_orchestrator(
    settings: FidesSettings | None = None,
) -> tuple[Any, Any]:
    """Create and return the compiled LangGraph StateGraph orchestrator with MCP tools.

    Returns a compiled LangGraph CompiledStateGraph that produces full
    hierarchical traces in LangSmith.
    """
    logger.info("Creating LangGraph orchestrator StateGraph")
    if settings is None:
        from fides.config.settings import get_settings

        settings = get_settings()

    mcp_client = MultiServerMCPClient(
        {
            "fides_tools": {
                "transport": "streamable_http",
                "url": settings.mcp_server_url,
            }
        }
    )

    workflow = StateGraph(FidesState)
    workflow.add_node("greeting_node", greeting_node)
    workflow.add_node("retrieve_node", retrieve_node)
    workflow.add_node("synthesize_node", synthesize_node)

    workflow.add_conditional_edges(
        START,
        route_intent,
        {
            "greeting_node": "greeting_node",
            "retrieve_node": "retrieve_node",
        },
    )
    workflow.add_edge("greeting_node", END)
    workflow.add_edge("retrieve_node", "synthesize_node")
    workflow.add_edge("synthesize_node", END)

    agent = workflow.compile()
    return agent, mcp_client
