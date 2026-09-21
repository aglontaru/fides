"""Unit tests for Orchestrator and AgentSystem."""

from __future__ import annotations

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage

from fides.agents.factory import AgentSystem, _trim_history_by_tokens
from fides.agents.orchestrator import is_simple_greeting, route_intent
from fides.config.settings import FidesSettings, LLMProvider


class ToolCallingFakeModel(GenericFakeChatModel):
    """Fake model that supports tool binding for deepagents."""

    def bind_tools(self, tools, **kwargs):
        return self


@pytest.mark.unit
def test_is_simple_greeting():
    """Verify greeting detection accurately classifies basic greetings."""
    assert is_simple_greeting("hi") is True
    assert is_simple_greeting("Hello there!") is True
    assert is_simple_greeting("Good morning") is True
    assert is_simple_greeting("What are the obligations under Article 16?") is False
    assert is_simple_greeting("Compare AI Act with MDR") is False


@pytest.mark.unit
def test_route_intent():
    """Verify intent routing heuristics."""
    g_intent = route_intent("hello!")
    assert g_intent.intent_type == "greeting"
    assert g_intent.requires_legal_review is False

    u_intent = route_intent("Please upload and index eu_ai_act.pdf")
    assert u_intent.intent_type == "upload"

    d_intent = route_intent("Can you diff and compare these two versions?")
    assert d_intent.intent_type == "diff"

    q_intent = route_intent("What are high-risk AI obligations?")
    assert q_intent.intent_type == "question"
    assert q_intent.requires_legal_review is True


@pytest.mark.unit
def test_trim_history_by_tokens():
    """Verify conversation history trimming respects token budget."""
    messages = [
        HumanMessage(content="A" * 400),  # ~110 tokens
        AIMessage(content="B" * 400),  # ~110 tokens
        HumanMessage(content="C" * 400),  # ~110 tokens
    ]
    # If budget is 250 tokens, the oldest message should be trimmed
    trimmed = _trim_history_by_tokens(messages, max_tokens=250)
    assert len(trimmed) == 2
    assert trimmed[0].content == "B" * 400
    assert trimmed[1].content == "C" * 400


@pytest.mark.unit
@pytest.mark.asyncio
async def test_agent_system_chat_fast_greeting():
    """Verify simple greetings bypass complex agent delegation."""
    fake_llm = ToolCallingFakeModel(
        messages=iter([AIMessage(content="Hello! I am Fides, your legal intelligence assistant.")])
    )
    system = AgentSystem(
        agent=None,
        mcp_client=None,
        llm=fake_llm,
        settings=FidesSettings(llm_provider=LLMProvider.OLLAMA),
        conversation_history=[],
    )

    chunks = []
    async for chunk in system.chat("Hello there!"):
        chunks.append(chunk)

    full_res = "".join(chunks)
    assert "Fides" in full_res
    assert len(system.conversation_history) == 2
    assert system.conversation_history[0].content == "Hello there!"


@pytest.mark.unit
def test_format_ingestion_confirmation():
    """Verify format_ingestion_confirmation builds structured output."""
    from fides.api.websocket import format_ingestion_confirmation
    from fides.ingestion.pipeline import IngestionResult

    result = IngestionResult(
        document_id="doc:MDR",
        short_name="MDR",
        document_title="Medical Devices Regulation",
        status="new_document",
        articles_count=123,
        paragraphs_count=456,
        recitals_count=78,
    )
    msg = format_ingestion_confirmation(result, "MDR_act.pdf")
    assert "MDR_act.pdf" in msg
    assert "Medical Devices Regulation" in msg
    assert "MDR" in msg
    assert "Articles: 123" in msg
    assert "Recitals: 78" in msg
    assert "Paragraphs: 456" in msg
    assert "Sample questions" in msg or "sample questions" in msg
