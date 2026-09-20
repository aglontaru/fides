"""Tests for the fides.config package."""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from fides.config.settings import FidesSettings, LLMProvider, get_settings


@pytest.mark.unit
def test_fides_settings_defaults():
    """Test FidesSettings loads defaults correctly."""
    settings = FidesSettings(_env_file=None, gemini_api_key=SecretStr("test_key"))
    assert settings.llm_provider == LLMProvider.OLLAMA
    assert settings.ollama_base_url == "http://ollama:11434"


@pytest.mark.unit
def test_fides_settings_gemini_requires_api_key():
    """Test FidesSettings validates gemini requires API key."""
    with pytest.raises(ValueError, match="GEMINI_API_KEY is required"):
        FidesSettings(llm_provider=LLMProvider.GEMINI, gemini_api_key=None)


@pytest.mark.unit
def test_llm_provider_enum_values():
    """Test LLMProvider enum values."""
    assert LLMProvider.OLLAMA == "ollama"
    assert LLMProvider.GEMINI == "gemini"


@pytest.mark.unit
def test_get_settings_caching():
    """Test get_settings caching."""
    settings_1 = get_settings()
    settings_2 = get_settings()
    assert settings_1 is settings_2


@pytest.mark.unit
def test_effective_llm_model():
    """Test effective_llm_model property for both providers."""
    ollama_settings = FidesSettings(llm_provider=LLMProvider.OLLAMA, llm_model="test-model")
    assert ollama_settings.effective_llm_model == "test-model"

    gemini_settings = FidesSettings(
        llm_provider=LLMProvider.GEMINI,
        gemini_model="gemini-2.5-flash",
        gemini_api_key=SecretStr("test"),
    )
    assert gemini_settings.effective_llm_model == "gemini-2.5-flash"


@pytest.mark.unit
def test_settings_from_env(monkeypatch):
    """Test settings from environment variables."""
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "env_test_key")
    settings = FidesSettings()
    assert settings.llm_provider == LLMProvider.GEMINI
    assert settings.gemini_api_key.get_secret_value() == "env_test_key"
