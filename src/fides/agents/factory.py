import inspect
from collections.abc import AsyncIterator, Callable
from typing import Any

import structlog
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from pydantic import BaseModel, ConfigDict

from fides.agents.orchestrator import create_orchestrator
from fides.config import create_chat_model
from fides.config.settings import FidesSettings

logger = structlog.get_logger(__name__)


async def _notify_status(callback: Callable[[str], Any] | None, message: str) -> None:
    """Safely invoke status callback whether it is sync or async."""
    if callback is None:
        return
    try:
        res = callback(message)
        if inspect.isawaitable(res):
            await res
    except Exception as e:
        logger.debug(f"Status callback failed: {e}")

class AgentSystem(BaseModel):
    """Manages conversational chat, multi-turn history, and knowledge graph retrieval."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    agent: Any
    mcp_client: Any
    llm: Any = None
    settings: Any = None
    conversation_history: list[BaseMessage] = []

    async def chat(
        self,
        message: str,
        attachments: list[bytes] | None = None,
        on_status: Callable[[str], Any] | None = None,
    ) -> AsyncIterator[str]:
        """Stream response for a chat message using the compiled LangGraph Deep Agent.

        All turns are dispatched through self.agent (the LangGraph CompiledStateGraph),
        ensuring that LangSmith traces the complete multi-agent execution tree (nodes,
        sub-agents, tool executions, and state transitions).

        Args:
            message: The user's input message.
            attachments: Optional list of document attachments (bytes).
            on_status: Optional callback for status progress messages.

        Yields:
            Chunks of the agent's response string as they are generated.
        """
        logger.info("Processing chat message via LangGraph", message_length=len(message))
        clean_text = message.strip()
        if not clean_text:
            return

        await _notify_status(on_status, "Thinking...")

        # Build message history for LangGraph StateGraph
        messages = [
            *self.conversation_history[-8:],
            HumanMessage(content=clean_text),
        ]
        inputs = {"messages": messages}

        response_parts: list[str] = []
        try:
            async for ev in self.agent.astream_events(inputs, version="v2"):
                kind = ev["event"]
                name = ev.get("name", "")

                if kind == "on_chat_model_stream":
                    node = ev.get("metadata", {}).get("langgraph_node", "")
                    # Only stream conversational tokens intended for the user
                    if node in ("synthesize_node", "greeting_node", ""):
                        chunk = ev["data"]["chunk"]
                        tool_chunks = getattr(chunk, "tool_call_chunks", None)
                        content = getattr(chunk, "content", "")
                        if not tool_chunks and content and isinstance(content, str):
                            response_parts.append(content)
                            yield content

                elif kind == "on_tool_start":
                    tool_input = ev["data"].get("input")
                    if isinstance(tool_input, dict) and "query_text" in tool_input:
                        q_text = tool_input["query_text"]
                        await _notify_status(
                            on_status, f"Searching knowledge graph for '{q_text}'..."
                        )
                    elif isinstance(tool_input, dict) and "task" in tool_input:
                        task_desc = str(tool_input["task"])[:60]
                        await _notify_status(
                            on_status, f"Delegating task to subagent: {task_desc}..."
                        )
                    else:
                        await _notify_status(on_status, f"Calling tool: {name}...")

                elif kind == "on_tool_end":
                    await _notify_status(on_status, "Processing retrieved legal context...")

        except Exception as stream_err:
            logger.error(f"Error streaming LangGraph response: {stream_err}")

        full_res = "".join(response_parts).strip()
        if not full_res:
            full_res = (
                "I processed your query against the knowledge graph, but could not formulate a response. "
                "Please verify your question or rephrase."
            )
            yield full_res

        self.conversation_history.append(HumanMessage(content=clean_text))
        self.conversation_history.append(AIMessage(content=full_res))


    async def close(self) -> None:
        """Close the MCP client connection and perform cleanup."""
        logger.info("Closing AgentSystem")
        if hasattr(self.mcp_client, "close") and callable(self.mcp_client.close):
            await self.mcp_client.close()


async def create_agent_system(settings: FidesSettings | None = None) -> AgentSystem:
    """Create the complete Fides agent system.

    Returns an AgentSystem that manages the orchestrator, MCP connection,
    and provides methods for chat interaction.
    """
    logger.info("Creating full agent system")
    if settings is None:
        from fides.config.settings import get_settings

        settings = get_settings()
    agent, mcp_client = await create_orchestrator(settings)
    llm = create_chat_model(settings)

    return AgentSystem(
        agent=agent,
        mcp_client=mcp_client,
        llm=llm,
        settings=settings,
        conversation_history=[],
    )
