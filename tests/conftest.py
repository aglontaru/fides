"""Shared pytest fixtures for the Fides test suite."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import SecretStr

from fides.config.settings import FidesSettings, LLMProvider


@pytest.fixture
def settings() -> FidesSettings:
    """Fixture providing FidesSettings with test-appropriate defaults."""
    return FidesSettings(
        llm_provider=LLMProvider.OLLAMA,
        llm_model="llama3.1",
        ollama_base_url="http://localhost:11434",
        neo4j_uri="bolt://localhost:7687",
        neo4j_user="neo4j",
        neo4j_password=SecretStr("password"),
    )


@pytest.fixture
def mock_neo4j_driver() -> MagicMock:
    """Mock of neo4j async driver with session and transaction mocks."""
    driver = MagicMock()
    session = AsyncMock()
    tx = AsyncMock()

    session.__aenter__.return_value = session
    session.begin_transaction.return_value.__aenter__.return_value = tx
    driver.session.return_value = session

    return driver


@pytest.fixture
def sample_legislation_text() -> str:
    """A realistic excerpt of EU AI Act text."""
    return """TITLE I
GENERAL PROVISIONS

Article 1
Subject matter

1. The purpose of this Regulation is to ensure the free movement of AI systems.

2. This Regulation lays down:
(a) harmonised rules for the placing on the market;
(b) prohibitions of certain artificial intelligence practices.

Article 2
Scope

This Regulation applies to providers placing on the market AI systems in the Union.

Article 3
Definitions

For the purposes of this Regulation, the following definitions apply:
(1) 'artificial intelligence system' means a machine-based system designed to operate with varying levels of autonomy;
(2) 'provider' means a natural or legal person who develops an AI system.
"""


@pytest.fixture
def sample_pdf_bytes() -> bytes:
    """Fixture that simulates reading a small test PDF."""
    return b"%PDF-1.4\n%...\n"


@pytest.fixture
def mock_embeddings() -> MagicMock:
    """Mock embeddings model that returns fixed-dimension vectors."""
    embeddings = MagicMock()
    embeddings.embed_documents.return_value = [[0.1] * 768 for _ in range(5)]
    embeddings.embed_query.return_value = [0.1] * 768
    return embeddings
