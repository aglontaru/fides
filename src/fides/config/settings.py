"""Fides configuration — Pydantic Settings loaded from environment / .env file."""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Self

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProvider(StrEnum):
    """Supported LLM providers."""

    OLLAMA = "ollama"
    GEMINI = "gemini"


class FidesSettings(BaseSettings):
    """Central configuration for the Fides system.

    All values can be overridden via environment variables or a ``.env`` file
    located at the project root.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── LLM ───────────────────────────────────────────────────────────
    llm_provider: LLMProvider = LLMProvider.OLLAMA
    llm_model: str = "llama3.1"
    ollama_base_url: str = "http://ollama:11434"

    # Gemini
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-2.5-flash"

    # ── Agents ────────────────────────────────────────────────────────
    # Agent budgets
    agent_max_replans: int = 2
    agent_max_task_retries: int = 2
    agent_max_tool_calls: int = 8
    agent_task_timeout: int = 120

    # Per-agent LLM overrides (optional)
    legal_agent_model: str | None = None
    query_agent_model: str | None = None
    indexing_agent_model: str | None = None
    diff_agent_model: str | None = None

    # Conversation memory
    max_conversation_tokens: int = 16000

    # ── Embeddings ────────────────────────────────────────────────────
    embedding_provider: LLMProvider = LLMProvider.OLLAMA
    embedding_model: str = "nomic-embed-text"
    embedding_dimensions: int = 768

    # ── Neo4j ─────────────────────────────────────────────────────────
    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: SecretStr = SecretStr("fides-dev-password")

    # ── MCP ───────────────────────────────────────────────────────────
    mcp_server_url: str = "http://mcp-server:8000/sse"

    # ── LangSmith ─────────────────────────────────────────────────────
    langsmith_tracing: bool = True
    langsmith_endpoint: str = "https://eu.api.smith.langchain.com"
    langsmith_api_key: SecretStr | None = None
    langsmith_project: str = "Fides"

    # ── Application ───────────────────────────────────────────────────
    log_level: str = "INFO"
    fides_api_host: str = "0.0.0.0"  # noqa: S104 — intentional bind-all for Docker
    fides_api_port: int = 8080
    document_storage_path: Path = Path("./documents")

    # ── Validation ────────────────────────────────────────────────────
    @model_validator(mode="after")
    def _validate_provider_config(self) -> Self:
        """Ensure provider-specific credentials are present."""
        if self.llm_provider == LLMProvider.GEMINI and not self.gemini_api_key:
            msg = "GEMINI_API_KEY is required when LLM_PROVIDER=gemini"
            raise ValueError(msg)
        return self

    @property
    def effective_llm_model(self) -> str:
        """Return the model name for the active provider."""
        if self.llm_provider == LLMProvider.GEMINI:
            return self.gemini_model
        return self.llm_model


@lru_cache(maxsize=1)
def get_settings() -> FidesSettings:
    """Return a cached singleton of the application settings."""
    return FidesSettings()
