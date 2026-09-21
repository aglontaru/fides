# Fides Architecture

## System Architecture

Fides is organised as an **autonomous multi-agent legal intelligence platform** powered by LangChain Deep Agents and LangGraph, operating on a unified **Neo4j 5 knowledge graph** exposed via FastMCP.

The platform is designed to process, index, and reason across legal instruments from **any jurisdiction** (EU, US, UK, codes, statutes, regulations, standards, and commercial contracts).

### Component Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Docker Compose Stack                              │
│                                                                             │
│  ┌─────────────┐  ┌──────────────────┐  ┌────────────────────────────────┐  │
│  │   Ollama     │  │   Neo4j 5        │  │   Fides FastMCP Tool Server    │  │
│  │   (LLM/Emb)  │  │   (Graph + Vec)  │  │   (:8000 / HTTP SSE)           │  │
│  │   :11434     │  │   :7474 / :7687  │  │   vector · neo4j · diff tools  │  │
│  └──────┬──────┘  └────────┬─────────┘  └──────────────┬─────────────────┘  │
│         │                  │                           │                    │
│         │         ┌────────┴───────────────────────────┘                    │
│         │         │                                                         │
│  ┌──────┴─────────┴──────────────────────────────────────────────────────┐  │
│  │                 Fides Autonomous Agent Service (:8080)                │  │
│  │                                                                       │  │
│  │  ┌─────────────────────────────────────────────────────────────────┐  │  │
│  │  │                  FastAPI + WebSocket Gateway                    │  │  │
│  │  └─────────────────────────────┬───────────────────────────────────┘  │  │
│  │                                │                                      │  │
│  │  ┌─────────────────────────────▼───────────────────────────────────┐  │  │
│  │  │                   Orchestrator Agent (DeepAgent)                │  │  │
│  │  │             Dynamic Intent Classification · ToDo Planning       │  │  │
│  │  │             Deliberation Gate · Lossless Evidence Assembler     │  │  │
│  │  │                                                                 │  │  │
│  │  │   ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────┐ │  │  │
│  │  │   │  Query   │ │  Legal   │ │  Graph   │ │ Indexing │ │ Diff  │ │  │  │
│  │  │   │Sub-Agent │ │Sub-Agent │ │ Builder  │ │Sub-Agent │ │Sub-Ag │ │  │  │
│  │  │   └──────────┘ └──────────┘ └──────────┘ └──────────┘ └───────┘ │  │  │
│  │  └─────────────────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## The 6 Autonomous Agents

All agents are constructed using the standard **RISEN** framework (Role, Instructions, Situation, Expected Outcome, Nuances) and communicate via typed Pydantic contracts (`fides.agents.contracts`).

### 1. Orchestrator Agent
The conversational entrypoint and reasoning engine:
- **Dynamic Intent Extraction**: Identifies user intent (`question`, `upload`, `diff`, `greeting`, `help`, `removal`) dynamically via prompt reasoning (no static pipeline regex).
- **ToDo Formulation & Execution**: Plans task dependencies and delegates sequentially to sub-agents via the `task()` tool.
- **Deliberation Gate**: Intercepts substantive legal inquiries, enforces comprehensive retrieval from the knowledge graph, executes ReAct cross-reference graph traversal, and coordinates final synthesis via the Legal Agent.
- **Conversation Memory**: Maintains multi-turn context trimmed to configured token budgets.

### 2. Query Agent
Legal retrieval and statutory evidence specialist:
- **Multi-Angle ReAct Search**: Decomposes complex queries across 4 quadrants:
  1. *Operative Definitions* (defined terms, actor roles).
  2. *Primary Obligations & Standards* (duties, conformity procedures).
  3. *Statutory Exemptions & Negative Qualifiers* (carve-outs, "other than", "except", "shall not apply").
  4. *Supplemental Annexes & Recitals* (schedules, legislative intent).
- **Reciprocal Rank Fusion (RRF)**: Combines dense vector similarity across Article, Paragraph, Annex, and Recital indexes with BM25 fulltext matching (`1 / (60 + rank)`).
- **Cross-Reference Traversal**: Follows `cited_articles` and `referenced_annexes` to assemble complete context.

### 3. Legal Agent
Mandatory quality gate and statutory auditor embodying the NotebookLM standard:
- **Exemption & Negative Qualifier Audit**: Scrutinizes statutory carve-outs (e.g. verifying whether custom-made devices are excluded from general CE marking rules pursuant to Art. 20(1)).
- **Entity Liability Chain**: Audits joint and several liabilities (e.g. non-EU manufacturer failures triggering Authorised Representative liability under Art. 11(5)).
- **Client-Ready Legal Memoranda**: Drafts structured briefs (Executive Summary, Operative Legal Analysis, Statutory Exemptions & Special Regimes, Procedural & Documentary Requirements).
- **Deterministic Inline Citations**: Mandates exact citations in `[Document, Provision/Section/Art. X, Para. Y]` format for every substantive legal assertion.

### 4. Graph Builder Agent
Dynamic ontology discovery specialist:
- **Zero Hardcoded Assumptions**: Operates dynamically across any legal jurisdiction (EU, US, UK, contracts).
- **Entity & Role Discovery**: Discovers novel `ActorRole`s (e.g. `Manufacturer`, `AuthorisedRepresentative`, `Borrower`), `DefinedTerm`s, and `Obligation`s.
- **Semantic Relationship Modeling**: Links entities back to originating provisions using `[:IMPOSES]`, `[:EXEMPTS_FROM]`, `[:APPLIES_TO]`, `[:DEFINES]`, and `[:CITES]`.
- **Schema Registration**: Dynamically updates the Neo4j ontology catalog via `upsert_ontology_schema`.

### 5. Indexing Agent
Universal document ingestion and lifecycle manager:
- **Hierarchical Ingestion Pipeline**: Ingests legal PDFs and text into the structural graph (`Document` → `Chapter` → `Section` → `Article` → `Paragraph`, plus `Annex` and `Recital`).
- **Vector Embeddings**: Computes and stores embeddings for all operative text units.
- **Content Hash Deduplication**: Computes SHA-256 hashes to prevent duplicate indexation.
- **Document Removal**: Handles atomic cascade deletions of subgraphs when documents are removed.

### 6. Diff Agent
Comparative legal analyst:
- **Multi-Level Comparison**: Performs article-level and paragraph-level diffing between document versions or related statutes.
- **Semantic Similarity Scoring**: Uses vector cosine similarity to track amended provisions.
- **Normative Impact Assessment**: Identifies additions, deletions, and alterations in legal obligations, exemptions, and definitions.

---

## Data Flow & Deliberation Architecture

### 1. Document Ingestion Flow
```
User uploads document
    │
    ▼
Orchestrator → delegates to Diff Agent
    │
    ├── Result: "identical_document" → Informs user document is already indexed.
    ├── Result: "updated_document"   → Computes diff, updates changed provisions.
    └── Result: "new_document"
          │
          ▼
        Indexing Agent
          ├── Parses document into structural hierarchy
          ├── Extracts metadata, defined terms, and citations
          ├── Computes SHA-256 content hashes & vector embeddings
          └── Writes nodes & edges to Neo4j
          │
          ▼
        Graph Builder Agent
          ├── Analyzes text for novel actor roles, obligations, and terms
          └── Links semantic relationships into the graph
```

### 2. Deliberation & Grounded Query Flow
```
User asks legal question
    │
    ▼
Orchestrator Agent (Dynamic Intent Extraction via RISEN prompt)
    │
    ▼
Query Agent
    ├── Executes RRF Hybrid Search (Vector + Fulltext across Articles, Paras, Annexes)
    └── Traverses cross-referenced provisions (e.g. Annex XIII, Art. 11(5))
    │
    ▼
Lossless Evidence Assembler
    ├── Prioritizes top-scoring provisions
    ├── Budgets evidence payload (~24,000 chars / ~6,000 tokens)
    └── Prunes peripheral branches to prevent context window blowout
    │
    ▼
Deliberation Gate (Legal Agent Quality Audit)
    ├── Audits negative qualifiers & statutory exemptions (e.g. Art. 20(1) CE mark carve-out)
    ├── Verifies entity liability rules (e.g. Art. 11(5) Authorised Representative joint liability)
    ├── Verifies that all conclusions have exact inline citations
    └── Outputs client-facing legal memorandum
```

---

## Technology Stack

| Layer | Component | Technology | Purpose |
| :--- | :--- | :--- | :--- |
| **Agent Orchestration** | DeepAgent + LangGraph | LangChain DeepAgents, LangGraph | Autonomous multi-agent coordination |
| **Tool Protocol** | FastMCP | FastMCP (streamable-http) | Standardized tool invocation layer |
| **Knowledge Graph** | Neo4j 5 Community | Neo4j, Cypher, APOC | Dual-layer structural + semantic graph |
| **Vector Search** | Neo4j Vector Indexes | Cosine similarity on 768-dim embeddings | Dense semantic retrieval |
| **Fulltext Search** | Neo4j Fulltext Indexes | Lucene BM25 on articles, paras, annexes | Keyword & phrase matching |
| **LLM Provider** | Multi-Provider Engine | Ollama (`qwen2.5:3b`), Google Gemini | Decoupled local / cloud inference |
| **Configuration** | Centralized Agent Config | YAML (`agents.yaml`) + Pydantic v2 | Per-agent model, timeout, retry controls |
| **API & Streaming** | FastAPI Gateway | FastAPI, WebSocket, uvicorn | Real-time chat & token streaming |
| **Observability** | Structured Logging & Tracing | structlog, LangSmith | Step-level agent telemetry |
