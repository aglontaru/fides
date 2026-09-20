# Fides — Legislation Knowledge Graph RAG System

<p align="center">
  <strong>A multi-agent system for indexing, managing, and querying legislation documents using a Neo4j knowledge graph.</strong>
</p>

<p align="center">
  Built with LangChain Deep Agents · Neo4j · FastMCP · FastAPI<br/>
  <em>by Alex Glontaru · Rematiq (Berlin)</em>
</p>

---

## Overview

**Fides** (Latin: *trust*) is an agentic RAG system purpose-built for EU legislation. Upload a regulation — EU AI Act, Medical Device Regulation, GDPR — and Fides will:

1. **Parse & index** the document into a hierarchical knowledge graph (Title → Chapter → Section → Article → Paragraph)
2. **Detect duplicates & diffs** — if you upload a document that's already indexed, Fides identifies what changed at the article level
3. **Answer questions** with precise citations — every claim references `[Document, Art. X, Para. Y]`

The system is organized as **4 autonomous agents** sharing a common MCP tool server:

| Agent | Role |
|-------|------|
| **Orchestrator** | Conversational interface — routes intents to sub-agents |
| **Indexing Agent** | Parses documents, builds the knowledge graph |
| **Diff Agent** | Deduplication and change detection |
| **QA Agent** | Answers legal questions with cited sources |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    User (WebSocket Chat)                     │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                   Orchestrator Agent                         │
│              (conversation routing + delegation)             │
│                                                              │
│    ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │
│    │ Indexing Agent│ │  Diff Agent  │ │   QA Agent   │       │
│    └──────┬───────┘ └──────┬───────┘ └──────┬───────┘       │
└───────────┼────────────────┼────────────────┼───────────────┘
            │                │                │
            ▼                ▼                ▼
┌─────────────────────────────────────────────────────────────┐
│              MCP Tool Server (FastMCP / HTTP)                │
│                                                              │
│  neo4j_query · vector_search · parse_document · diff_docs   │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│              Neo4j (Graph + Vector Index)                     │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) & Docker Compose
- [uv](https://docs.astral.sh/uv/) (Python package manager)

### 1. Clone & configure

```bash
git clone <repo-url> fides
cd fides
cp .env.example .env
# Edit .env with your API keys (Gemini, LangSmith)
```

### 2. Start all services

```bash
# Start Neo4j, MCP server, agents API, and Ollama
docker compose up -d --build

# Pull the default Ollama model (first time only)
docker compose exec ollama ollama pull llama3.1
docker compose exec ollama ollama pull nomic-embed-text
```

### 3. Open the chat UI

Navigate to **http://localhost:8080** in your browser.

- Upload a PDF of legislation (drag & drop or click upload)
- Ask questions like: *"What are the obligations for providers of high-risk AI systems?"*
- View precise citations with every answer

### 4. Switch LLM provider

```bash
# In .env:
LLM_PROVIDER=gemini
GEMINI_API_KEY=your-key-here
GEMINI_MODEL=gemini-2.5-flash

# Restart agents service
docker compose restart agents
```

## Development

### Setup

```bash
# Install all dependencies (including dev)
make setup

# Install pre-commit hooks
uv run pre-commit install
```

### Running tests

```bash
make test-unit          # Fast unit tests (no Docker needed)
make test-integration   # Integration tests (requires docker compose up)
make test               # All tests with coverage
make eval               # Agent evaluation suite
```

### Code quality

```bash
make lint               # Ruff lint + format check
make typecheck          # MyPy strict mode
make format             # Auto-format code
```

### Useful commands

```bash
make up                 # docker compose up -d --build
make down               # docker compose down
make logs               # Tail agent logs
make seed               # Seed Neo4j with sample legislation
make clean              # Remove caches and build artifacts
```

## Project Structure

```
fides/
├── src/fides/
│   ├── config/          # Settings, LLM factory, logging
│   ├── graph/           # Neo4j schema, models, operations
│   ├── ingestion/       # Document parsers, legislation chunkers
│   ├── mcp_server/      # Shared MCP tool server
│   ├── agents/          # Deep Agents (orchestrator + sub-agents)
│   └── api/             # FastAPI + WebSocket + chat UI
├── tests/
│   ├── unit/            # Fast, isolated tests
│   ├── integration/     # Tests requiring Docker services
│   └── evals/           # Agent evaluation benchmarks
├── docker/              # Dockerfiles + Neo4j init
├── scripts/             # Utility scripts
└── docs/                # Architecture & schema docs
```

## Knowledge Graph Schema

Fides models legislation as a hierarchical graph in Neo4j:

```
Document → Title → Chapter → Section → Article → Paragraph → Point
                                          │
                                          ├── DEFINES → DefinedTerm
                                          ├── IMPOSES → Obligation → APPLIES_TO → ActorRole
                                          ├── CITES → Article (cross-reference)
                                          └── INTERPRETED_BY → Recital
```

Each `Article` and `Paragraph` node carries a vector embedding for semantic search, plus a content hash for change detection.

## Observability

- **Structured logging** via `structlog` — JSON output in Docker, coloured console in dev
- **LangSmith** tracing (optional) — see every agent step, tool call, and LLM interaction
- **Neo4j Browser** — http://localhost:7474 for graph visualization

## Configuration Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `ollama` | `ollama` or `gemini` |
| `LLM_MODEL` | `llama3.1` | Model name for Ollama |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Model name for Gemini |
| `GEMINI_API_KEY` | — | Required for Gemini |
| `NEO4J_URI` | `bolt://neo4j:7687` | Neo4j connection |
| `MCP_SERVER_URL` | `http://mcp-server:8000/mcp` | MCP tool server |
| `LANGSMITH_API_KEY` | — | Optional tracing |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

## License

MIT

---

<sub>Built with ❤️ by Rematiq · Berlin</sub>
