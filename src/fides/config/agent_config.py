"""Agent configuration schema and loader.

Allows developers to customize models, timeouts, retry limits, and tool budgets
per agent via `agents.yaml`.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import structlog
import yaml
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


class AgentLimitConfig(BaseModel):
    """Runtime limits and LLM settings for an individual agent."""

    model: str | None = None
    temperature: float = 0.0
    timeout_seconds: int = 120
    max_retries: int = 2
    max_tool_calls: int = 8
    description: str = ""


class GlobalAgentSettings(BaseModel):
    """Global multi-agent runtime parameters."""

    max_conversation_tokens: int = 16000
    enable_deliberation_gate: bool = True


class AgentsConfig(BaseModel):
    """Container for all agent limits and global agent settings."""

    orchestrator: AgentLimitConfig = Field(
        default_factory=lambda: AgentLimitConfig(
            max_tool_calls=10, description="Master coordinator and intent planner"
        )
    )
    query: AgentLimitConfig = Field(
        default_factory=lambda: AgentLimitConfig(
            timeout_seconds=90, description="Legal retrieval specialist across vectors and graph"
        )
    )
    legal: AgentLimitConfig = Field(
        default_factory=lambda: AgentLimitConfig(
            description="Mandatory quality gate, evidence critique, and citation drafter"
        )
    )
    indexing: AgentLimitConfig = Field(
        default_factory=lambda: AgentLimitConfig(
            timeout_seconds=180,
            max_tool_calls=12,
            description="Ingestion and document lifecycle manager",
        )
    )
    graph_builder: AgentLimitConfig = Field(
        default_factory=lambda: AgentLimitConfig(
            timeout_seconds=180,
            max_tool_calls=12,
            description="Dynamic ontology discovery and knowledge graph expander",
        )
    )
    diff: AgentLimitConfig = Field(
        default_factory=lambda: AgentLimitConfig(
            timeout_seconds=90,
            max_tool_calls=6,
            description="Document version comparison and normative impact specialist",
        )
    )
    global_settings: GlobalAgentSettings = Field(default_factory=GlobalAgentSettings)

    def get_agent_limit(self, agent_name: str) -> AgentLimitConfig:
        """Retrieve limit config for a named agent with fallback."""
        mapping = {
            "orchestrator": self.orchestrator,
            "query": self.query,
            "legal": self.legal,
            "indexing": self.indexing,
            "graph_builder": self.graph_builder,
            "diff": self.diff,
        }
        return mapping.get(agent_name, AgentLimitConfig())


def _find_agents_yaml_path() -> Path | None:
    """Locate agents.yaml from env, cwd, or repository root."""
    env_path = os.getenv("FIDES_AGENTS_CONFIG")
    if env_path and Path(env_path).is_file():
        return Path(env_path)

    candidates = [
        Path.cwd() / "agents.yaml",
        Path(__file__).resolve().parents[3] / "agents.yaml",
        Path("/app/agents.yaml"),
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


@lru_cache(maxsize=1)
def load_agent_config(config_path: Path | str | None = None) -> AgentsConfig:
    """Load and cache agent runtime configuration from agents.yaml."""
    target_path = Path(config_path) if config_path else _find_agents_yaml_path()

    if not target_path or not target_path.is_file():
        logger.debug("No agents.yaml found, using built-in defaults")
        return AgentsConfig()

    try:
        raw_text = target_path.read_text(encoding="utf-8")
        data: dict[str, Any] = yaml.safe_load(raw_text) or {}

        agents_data = data.get("agents", {})
        global_data = data.get("global", {})

        return AgentsConfig(
            orchestrator=AgentLimitConfig(**agents_data.get("orchestrator", {})),
            query=AgentLimitConfig(**agents_data.get("query", {})),
            legal=AgentLimitConfig(**agents_data.get("legal", {})),
            indexing=AgentLimitConfig(**agents_data.get("indexing", {})),
            graph_builder=AgentLimitConfig(**agents_data.get("graph_builder", {})),
            diff=AgentLimitConfig(**agents_data.get("diff", {})),
            global_settings=GlobalAgentSettings(**global_data),
        )
    except Exception as e:
        logger.warning("Failed to parse agents.yaml, using defaults", error=str(e), path=str(target_path))
        return AgentsConfig()


__all__ = [
    "AgentLimitConfig",
    "AgentsConfig",
    "GlobalAgentSettings",
    "load_agent_config",
]
