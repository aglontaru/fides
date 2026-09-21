"""LLM and Embedding provider factory.

Instantiates the correct LangChain ``ChatModel`` and ``Embeddings`` based on the
active :pyclass:`FidesSettings` configuration.  This is the *only* module that
imports provider-specific packages — the rest of the codebase is provider-agnostic.
"""

from __future__ import annotations

import structlog
from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel

from fides.config.settings import FidesSettings, LLMProvider, get_settings

logger = structlog.get_logger(__name__)


def create_chat_model(settings: FidesSettings | None = None) -> BaseChatModel:
    """Create a chat model for the configured provider.

    Parameters
    ----------
    settings:
        Optional explicit settings.  Falls back to :func:`get_settings`.

    Returns
    -------
    BaseChatModel
        A LangChain chat model ready for tool-calling agents.
    """
    settings = settings or get_settings()

    match settings.llm_provider:
        case LLMProvider.OLLAMA:
            from langchain_ollama import ChatOllama

            logger.info(
                "llm.init",
                provider="ollama",
                model=settings.llm_model,
                base_url=settings.ollama_base_url,
            )
            return ChatOllama(
                model=settings.llm_model,
                base_url=settings.ollama_base_url,
                temperature=0.1,
                repeat_penalty=1.1,
            )

        case LLMProvider.GEMINI:
            from langchain_google_genai import ChatGoogleGenerativeAI

            assert settings.gemini_api_key is not None  # guaranteed by validator
            logger.info(
                "llm.init",
                provider="gemini",
                model=settings.gemini_model,
            )
            return ChatGoogleGenerativeAI(
                model=settings.gemini_model,
                google_api_key=settings.gemini_api_key.get_secret_value(),
                temperature=0.0,
                convert_system_message_to_human=False,
            )

        case _:  # pragma: no cover
            msg = f"Unsupported LLM provider: {settings.llm_provider}"
            raise ValueError(msg)


def create_agent_model(agent_name: str, settings: FidesSettings | None = None) -> BaseChatModel:
    """Create a chat model for a specific agent, using per-agent override if configured."""
    from fides.config.agent_config import load_agent_config

    s = settings or get_settings()
    agent_cfg = load_agent_config().get_agent_limit(agent_name)

    override_map = {
        "legal": s.legal_agent_model,
        "query": s.query_agent_model,
        "indexing": s.indexing_agent_model,
        "graph_builder": None,
        "diff": s.diff_agent_model,
        "orchestrator": None,
    }
    model_override = agent_cfg.model or override_map.get(agent_name)
    temperature = agent_cfg.temperature

    if model_override:
        # Override is in 'provider:model' format or just model name
        if ":" in model_override:
            provider, model_name = model_override.split(":", 1)
            if provider == "gemini":
                from langchain_google_genai import ChatGoogleGenerativeAI

                return ChatGoogleGenerativeAI(
                    model=model_name,
                    google_api_key=s.gemini_api_key.get_secret_value()
                    if s.gemini_api_key
                    else None,
                    temperature=temperature,
                    convert_system_message_to_human=False,
                )
            elif provider == "ollama":
                from langchain_ollama import ChatOllama

                return ChatOllama(
                    model=model_name,
                    base_url=s.ollama_base_url,
                    temperature=temperature,
                )
        # If no provider prefix, use the default provider with the specified model
        if s.llm_provider == LLMProvider.GEMINI:
            from langchain_google_genai import ChatGoogleGenerativeAI

            return ChatGoogleGenerativeAI(
                model=model_override,
                google_api_key=s.gemini_api_key.get_secret_value() if s.gemini_api_key else None,
                temperature=temperature,
                convert_system_message_to_human=False,
            )
        from langchain_ollama import ChatOllama

        return ChatOllama(model=model_override, base_url=s.ollama_base_url, temperature=temperature)
    # No override, use default chat model
    return create_chat_model(s)


def create_embeddings(settings: FidesSettings | None = None) -> Embeddings:
    """Create an embeddings model for the configured provider.

    Parameters
    ----------
    settings:
        Optional explicit settings.  Falls back to :func:`get_settings`.

    Returns
    -------
    Embeddings
        A LangChain embeddings instance.
    """
    settings = settings or get_settings()

    match settings.embedding_provider:
        case LLMProvider.OLLAMA:
            from langchain_ollama import OllamaEmbeddings

            logger.info(
                "embeddings.init",
                provider="ollama",
                model=settings.embedding_model,
            )
            return OllamaEmbeddings(
                model=settings.embedding_model,
                base_url=settings.ollama_base_url,
            )

        case LLMProvider.GEMINI:
            from langchain_google_genai import GoogleGenerativeAIEmbeddings

            assert settings.gemini_api_key is not None
            logger.info(
                "embeddings.init",
                provider="gemini",
                model=settings.embedding_model,
            )
            return GoogleGenerativeAIEmbeddings(
                model=settings.embedding_model,
                google_api_key=settings.gemini_api_key.get_secret_value(),
            )

        case _:  # pragma: no cover
            msg = f"Unsupported embedding provider: {settings.embedding_provider}"
            raise ValueError(msg)
