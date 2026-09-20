# Fides Architecture

## System Architecture

Fides is organised as a **multi-agent system** with four autonomous agents sharing
a common tool layer via the Model Context Protocol (MCP).

### Component Diagram

```
┌───────────────────────────────────────────────────────────────────────┐
│                         Docker Compose Stack                          │
│                                                                       │
│  ┌─────────────┐  ┌──────────────────┐  ┌──────────────────────────┐ │
│  │   Ollama     │  │   Neo4j 5        │  │   Fides MCP Server       │ │
│  │   (LLM)      │  │   (Graph + Vec)  │  │   (FastMCP / HTTP)       │ │
│  │   :11434     │  │   :7474 / :7687  │  │   :8000                  │ │
│  └──────┬───────┘  └────────┬─────────┘  └────────┬─────────────────┘ │
│         │                   │                      │                   │
│         │         ┌─────────┴──────────────────────┘                   │
│         │         │                                                    │
│  ┌──────┴─────────┴─────────────────────────────────────────────────┐ │
│  │                    Fides Agent Service                             │ │
│  │                                                                    │ │
│  │  ┌──────────────────────────────────────────────────────────────┐ │ │
│  │  │                 FastAPI + WebSocket (:8080)                   │ │ │
│  │  └──────────────────────────┬───────────────────────────────────┘ │ │
│  │                             │                                      │ │
│  │  ┌──────────────────────────▼───────────────────────────────────┐ │ │
│  │  │              Orchestrator Agent (Deep Agent)                  │ │ │
│  │  │                                                              │ │ │
│  │  │   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │ │ │
│  │  │   │  Indexing    │  │    Diff      │  │     QA      │        │ │ │
│  │  │   │  Sub-Agent   │  │  Sub-Agent   │  │  Sub-Agent  │        │ │ │
│  │  │   └─────────────┘  └─────────────┘  └─────────────┘        │ │ │
│  │  └──────────────────────────────────────────────────────────────┘ │ │
│  └────────────────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────────┘
```

## Agent Responsibilities

### Orchestrator Agent

The orchestrator is the user-facing conversational interface. It:

1. **Classifies user intent** — upload, question, list, help
2. **Delegates** to the appropriate sub-agent
3. **Synthesises** sub-agent results into a user-friendly response
4. **Manages** conversation state across turns

The orchestrator uses `deepagents.create_deep_agent()` with three configured
sub-agents. When it receives a user message, it plans which sub-agent(s)
to invoke using the built-in `task()` tool.

### Indexing Agent

Handles document ingestion into the knowledge graph:

1. Parse PDF / text → structured text via `parse_document` tool
2. Extract metadata, defined terms, cross-references via `extract_structure`
3. Chunk into legislation hierarchy via `chunk_legislation`
4. Write nodes and relationships to Neo4j via `neo4j_write`
5. Generate and store embeddings via `vector_upsert`

### Diff Agent

Handles deduplication and change detection:

1. Compute content hash via `compute_content_hash`
2. Check existence via `check_document_exists`
3. If similar document found, perform article-level diff via `diff_documents`
4. Report: `new` | `identical` | `updated` with change details

### QA Agent

Answers regulatory questions with precise citations:

1. Search knowledge graph via `hybrid_search` (vector + graph expansion)
2. Follow cross-references via `get_article_with_context`
3. Formulate answer with inline citations: `[EU AI Act, Art. 6, Para. 2]`
4. Explicitly state when information is insufficient

## Data Flow

### Document Upload Flow

```
User uploads PDF
    │
    ▼
Orchestrator → delegates to Diff Agent
    │
    ▼
Diff Agent:
    ├── compute_content_hash(document)
    ├── check_document_exists(hash, name)
    │
    ├── Result: "new_document"
    │     └── Orchestrator → delegates to Indexing Agent
    │           ├── extract_structure → metadata, terms, cross-refs
    │           ├── chunk_legislation → hierarchical chunks
    │           ├── neo4j_write → graph nodes + edges
    │           └── vector_upsert → embeddings
    │
    ├── Result: "identical_document"
    │     └── Orchestrator → "This document is already indexed."
    │
    └── Result: "updated_document"
          ├── diff_documents → changed articles list
          └── Orchestrator → delegates to Indexing Agent (partial re-index)
```

### Question Answering Flow

```
User asks question
    │
    ▼
Orchestrator → delegates to QA Agent
    │
    ▼
QA Agent:
    ├── hybrid_search(question, top_k=5)
    │     └── Returns: paragraphs + parent articles + chapters
    │         + recitals + definitions + cross-references
    │
    ├── (Optional) get_article_with_context(cross_referenced_article)
    │     └── Follow important cross-references for completeness
    │
    └── Synthesise answer with inline citations
          └── [EU AI Act, Art. 16, Para. 1]
```

## Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Agent Framework | `deepagents` + LangGraph | Orchestration, sub-agent delegation |
| Tool Protocol | FastMCP (streamable-http) | Shared tools across agents |
| Knowledge Graph | Neo4j 5 Community | Document structure + relationships |
| Vector Search | Neo4j Vector Index | Semantic similarity retrieval |
| LLM (Local) | Ollama | Development and demo |
| LLM (Cloud) | Google Gemini | Production alternative |
| API | FastAPI + WebSocket | Real-time chat interface |
| Logging | structlog | Structured JSON logging |
| Tracing | LangSmith | Agent step-level observability |

## LLM Provider Architecture

The system uses a **provider factory pattern** to decouple agent logic from
specific LLM implementations:

```python
# In fides/config/llm.py
def create_chat_model(settings) -> BaseChatModel:
    match settings.llm_provider:
        case "ollama": return ChatOllama(...)
        case "gemini": return ChatGoogleGenerativeAI(...)
```

Switching providers requires only changing `LLM_PROVIDER` in `.env`.
No code changes needed.
