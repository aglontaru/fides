"""Legal Sub-Agent for synthesis drafting, citation verification, and quality gating."""

from __future__ import annotations

from collections.abc import Sequence

import structlog
from deepagents.middleware.subagents import SubAgent
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool

from fides.agents.prompts import LEGAL_AGENT_SYSTEM_PROMPT
from fides.config.llm import create_agent_model
from fides.config.settings import FidesSettings, get_settings

logger = structlog.get_logger(__name__)

LEGAL_AGENT_DESCRIPTION = (
    "Mandatory legal drafting and verification specialist. Synthesizes authoritative legal prose "
    "grounded strictly in the retrieved legislative context provided to it. Formats citations with "
    "[Document, Art. X, Para. Y] notation, verifies that all assertions match cited text, checks for "
    "statutory exemptions/derogations, and evaluates regulatory completeness. Use this agent as the "
    "mandatory final gate to draft and verify responses for substantive legal questions."
)


def create_legal_subagent(
    tools: Sequence[BaseTool] | None = None,
    settings: FidesSettings | None = None,
    model: BaseChatModel | str | None = None,
) -> SubAgent:
    """Create a SubAgent specification for the Legal Agent compatible with DeepAgents.

    Args:
        tools: Optional tools (Legal Agent operates directly on provided context).
        settings: Application settings.
        model: Optional model override.

    Returns:
        SubAgent TypedDict configuration.
    """
    s = settings or get_settings()
    llm = model or create_agent_model("legal", s)

    logger.info("Configuring Legal subagent")

    return {
        "name": "legal",
        "description": LEGAL_AGENT_DESCRIPTION,
        "system_prompt": LEGAL_AGENT_SYSTEM_PROMPT,
        "tools": list(tools) if tools else [],
        "model": llm,
        "mode": "isolated",
    }


__all__ = [
    "LEGAL_AGENT_DESCRIPTION",
    "create_legal_subagent",
]
