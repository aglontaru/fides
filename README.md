<p align="center">
# Fides
## Universal Legal Intelligence & Knowledge Graph Platform
</p>

<p align="center">
  <strong>An autonomous multi-agent legal intelligence platform for indexing, analyzing, and querying legislation, regulations, codes, and contracts from any jurisdiction using a dynamic Neo4j knowledge graph.</strong>
</p>

<p align="center">
  Built with LangChain Deep Agents · Neo4j 5 · FastMCP · FastAPI · Pydantic v2<br/>
  by Alex Glontaru with ❤️ for Rematiq (Berlin)
</p>

---

## Overview

**Fides** (Latin: *trust / good faith*) is an autonomous legal intelligence system engineered to deliver **NotebookLM-grade statutory grounding** across legal texts from any jurisdiction — European Union, United States Federal and State law, United Kingdom statutes, international standards, or private commercial agreements.

Unlike conventional RAG systems that rely on naive text chunking and vector similarity alone, Fides organizes legal documents into a **dual-layer Neo4j knowledge graph**:
1. **Universal Structural Backbone**: Preserves the exact legislative hierarchy (`Document` → `Chapter` → `Section` → `Article` → `Paragraph`, plus `Annex` and `Recital`).
2. **Dynamic Semantic Layer**: Governed by an autonomous **Graph Builder Agent** that analyzes documents during ingestion to dynamically discover domain entities, actor roles, normative obligations, statutory exemptions, and relationship types without hardcoded jurisdictional assumptions.

### Key Capabilities

- **Universal Multi-Jurisdictional Ingestion**: Ingest and structure statutes, codes, directives, regulations, and contracts from any jurisdiction.
- **Dynamic Ontology Discovery**: An autonomous Graph Builder Agent dynamically extracts and links novel legal actor roles, definitions, and normative rules.
- **NotebookLM-Grade Grounding**: Every legal proposition is anchored with exact inline citations in `[Document, Provision/Section/Art. X, Para. Y]` format (e.g. `[MDR, Art. 20(1)]`, `[MDR, Annex XIII, Section 1]`).
- **Strict Exemption & Negative Qualifier Auditing**: Actively audits statutory carve-outs (e.g. *"devices, other than custom-made..."*, *"shall not apply"*, *"by way of derogation"*), preventing false generalizations.
- **Lossless Reciprocal Rank Fusion (RRF)**: Combines dense vector embeddings across Articles, Paragraphs, Annexes, and Recitals with BM25 fulltext search (`1 / (60 + rank)`).
- **Multi-Turn Collaborative Deliberation**: The 6 autonomous agents reason, act, cross-check, and expand cross-referenced provisions before synthesizing answers.
- **Developer Extensibility (`agents.yaml`)**: Centralized YAML configuration for agent models, budgets, retries, timeouts, and deliberation gate controls.

---

## Autonomous Agent Topology

Fides is powered by **6 specialized autonomous agents** interacting over structured Pydantic contracts:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            User (WebSocket / REST)                          │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
┌──────────────────────────────────────▼──────────────────────────────────────┐
│                            Orchestrator Agent                               │
│              (Intent Classification · Planning · ReAct Loop)                │
└──────┬──────────────┬──────────────┬──────────────┬──────────────┬──────────┘
       │              │              │              │              │
       ▼              ▼              ▼              ▼              ▼
┌─────────────┐┌─────────────┐┌─────────────┐┌─────────────┐┌─────────────┐
│ Query Agent ││ Legal Agent ││Graph Builder││  Indexing   ││ Diff Agent  │
│  (Multi-Q   ││  (Statutory ││ (Dynamic    ││  (Universal ││  (Semantic  │
│  Retrieval) ││   Auditor)  ││  Ontology)  ││  Ingestion) ││ Comparison) │
└──────┬──────┘└──────┬──────┘└──────┬──────┘└──────┬──────┘└──────┬──────┘
       │              │              │              │              │
       └──────────────┴──────────────┼──────────────┴──────────────┘
                                     │
                                     ▼
                    ┌─────────────────────────────────┐
                    │     FastMCP Tool Server (:8000) │
                    │   hybrid_search · get_provision │
                    │   diff_documents · neo4j_write  │
                    └────────────────┬────────────────┘
                                     │
                                     ▼
                    ┌─────────────────────────────────┐
                    │      Neo4j 5 Knowledge Graph    │
                    │   (Graph Hierarchy + Vectors)   │
                    └─────────────────────────────────┘
```

| Agent | Architecture | Primary Responsibilities |
| :--- | :--- | :--- |
| **Orchestrator Agent** | DeepAgent (LangGraph) | User-facing interface. Evaluates user intent dynamically via prompt reasoning, plans ToDo items, delegates tasks to sub-agents, and enforces the Deliberation Gate. |
| **Query Agent** | DeepAgent Subagent | Legal retrieval specialist. Executes multi-quadrant search (definitions, obligations, exemptions, annexes) via RRF hybrid search and traverses cross-referenced provisions. |
| **Legal Agent** | DeepAgent Subagent | Mandatory quality gate and statutory auditor. Audits negative qualifiers, validates operative exemptions, checks entity liabilities, and drafts citation-backed briefs. |
| **Graph Builder Agent** | DeepAgent Subagent | Dynamic ontology specialist. Discovers new actor roles, definitions, obligations, and domain-specific relationships (`[:IMPOSES]`, `[:EXEMPTS_FROM]`, `[:APPLIES_TO]`). |
| **Indexing Agent** | DeepAgent Subagent | Document lifecycle manager. Ingests PDFs/text, parses structural hierarchies, computes content hashes, and writes nodes/embeddings to Neo4j. |
| **Diff Agent** | DeepAgent Subagent | Document comparator. Tracks revisions, performs article-level and paragraph-level semantic diffing, and reports normative differences. |

---

## Standard Prompting Framework (RISEN)

All agent prompts strictly adhere to the 5-component **RISEN** framework:
- **R**ole: Specific identity, expertise, and authority boundaries.
- **I**nstructions: Step-by-step normative procedure and tool usage.
- **S**ituation: Environmental context and active document state.
- **E**xpected Outcome: Rigorous, verifiable output specification.
- **N**uances: Critical edge cases, negative qualifiers, and anti-hallucination constraints.

---

## Knowledge Graph Architecture

### 1. Structural Hierarchy
- `(:Document)`: Root node with title, short name, jurisdiction, publication date, and content hash.
- `(:Chapter)`, `(:Section)`: Structural groupings.
- `(:Article)`: Operative legislative articles with full text and vector embeddings.
- `(:Paragraph)`: Granular provision units with paragraph text and vector embeddings.
- `(:Annex)`: Schedules, appendices, and procedural annexes with full text and vector embeddings.
- `(:Recital)`: Legislative preambles, recitals, and statutory intent statements.

### 2. Dynamic Semantic Layer
- `(:DefinedTerm)`: Term name, definition text, and operative scope.
- `(:ActorRole)`: Legal entities (e.g. `Manufacturer`, `Authorised Representative`, `Data Controller`).
- `(:Obligation)`: Normative duties with legal modality (`MUST`, `SHALL`, `MAY`, `PROHIBITED`).
- Dynamic relationships: `[:DEFINES]`, `[:IMPOSES]`, `[:APPLIES_TO]`, `[:EXEMPTS_FROM]`, `[:CITES]`.

---

## Quick Start

### Prerequisites
- [Docker](https://www.docker.com/) & Docker Compose
- [uv](https://github.com/astral-sh/uv) (for local development)
- [Ollama](https://ollama.com/) (or Google Gemini API key)

### Running with Docker Compose

1. **Start the stack**:
   ```bash
   docker compose up -d --build
   ```

2. **Verify services**:
   - Web Chat UI: `http://localhost:8080` (or `http://localhost:3000`)
   - Health Check: `http://localhost:8080/health`
   - MCP Server: `http://localhost:8000`
   - Neo4j Browser: `http://localhost:7474` (user: `neo4j`, password: `fides-dev-password`)

### Local Development

1. **Install dependencies**:
   ```bash
   uv sync --all-extras
   ```

2. **Run linting, typechecking, and tests**:
   ```bash
   make check
   # or individually:
   make lint
   make typecheck
   make test-unit
   ```

3. **Configure Agent Limits (`agents.yaml`)**:
   Tune model limits, timeouts, retries, and deliberation behavior:
   ```yaml
   global_settings:
     enable_deliberation_gate: true
     max_conversation_tokens: 16000

   agents:
     orchestrator:
       timeout_seconds: 180
       max_tool_calls: 12
     legal:
       model: "ollama:qwen2.5:3b"
       temperature: 0.0
   ```

---

## Testing & Verification

- **Unit Tests**:
  ```bash
  uv run pytest tests/unit/ -v
  ```
- **Type Checking**:
  ```bash
  uv run mypy src/fides
  ```
- **Live WebSocket Query Verification**:
  ```bash
  uv run python scratch/test_live_query.py
  ```

---

## License

Apache License 2.0. See [LICENSE](LICENSE) for details.
