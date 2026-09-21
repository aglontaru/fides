"""Unit tests for chat stream filtering to guarantee no internal monologue leak."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessageChunk

from fides.agents.factory import AgentSystem


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stream_filters_out_tool_preambles():
    """Verify that tokens generated in a turn that invokes tools are discarded, not streamed."""
    mock_agent = MagicMock()

    # Simulate 2 turns from the model:
    # Turn 1: Preliminary monologue + Tool Call (must be discarded!)
    # Turn 2: Final synthesized answer (must be streamed!)
    async def mock_astream_events(inputs, version="v2"):
        # Turn 1: chat model starts
        yield {"event": "on_chat_model_start", "run_id": "run-1", "metadata": {}}
        yield {
            "event": "on_chat_model_stream",
            "run_id": "run-1",
            "data": {"chunk": AIMessageChunk(content="To address your query... Let's use the query agent.")},
            "metadata": {},
        }
        # Turn 1 ends with a tool call
        yield {
            "event": "on_chat_model_end",
            "run_id": "run-1",
            "data": {
                "output": MagicMock(
                    tool_calls=[{"name": "task", "args": {"subagent_type": "query"}}]
                )
            },
            "metadata": {},
        }

        # Tool execution events
        yield {
            "event": "on_tool_start",
            "name": "task",
            "data": {"input": {"subagent_type": "query", "description": "Search custom-made devices"}},
        }
        yield {
            "event": "on_tool_end",
            "name": "task",
            "data": {"input": {"subagent_type": "query"}},
        }

        # Turn 2: chat model starts (final turn)
        yield {"event": "on_chat_model_start", "run_id": "run-2", "metadata": {}}
        yield {
            "event": "on_chat_model_stream",
            "run_id": "run-2",
            "data": {"chunk": AIMessageChunk(content="Custom-made devices are exempt from CE marking pursuant to [MDR, Art. 21(1)].")},
            "metadata": {},
        }
        # Turn 2 ends with NO tool calls
        yield {
            "event": "on_chat_model_end",
            "run_id": "run-2",
            "data": {"output": MagicMock(tool_calls=[])},
            "metadata": {},
        }

    mock_agent.astream_events = mock_astream_events

    system = AgentSystem(
        agent=mock_agent,
        mcp_client=MagicMock(),
    )

    yielded_chunks = []
    status_updates = []
    async for chunk in system.chat(
        "What are the requirements for custom-made devices?",
        on_status=lambda s: status_updates.append(s),
    ):
        yielded_chunks.append(chunk)

    full_output = "".join(yielded_chunks)

    # Monologue from Turn 1 must NOT appear in final output
    assert "To address your query" not in full_output
    assert "query agent" not in full_output
    assert "Let's use" not in full_output

    # Verified response from Turn 2 MUST appear
    assert "Custom-made devices are exempt from CE marking pursuant to [MDR, Art. 21(1)]." in full_output

    # Status notifications must be user-friendly without internal agent names
    for status in status_updates:
        assert "query agent" not in status.lower()
