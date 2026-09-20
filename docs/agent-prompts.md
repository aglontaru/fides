# Agent System Prompts

This document records the system prompts used by each Fides agent.
Prompts are defined in `src/fides/agents/prompts.py`.

## Prompt Design Principles

1. **Role clarity** — Each agent has a single, well-defined responsibility.
2. **Tool awareness** — Prompts reference the specific MCP tools the agent should use.
3. **Citation rigour** — The QA agent is explicitly instructed to cite every claim.
4. **Safety boundaries** — Agents are told never to fabricate legal provisions.
5. **Professional tone** — Suitable for regulatory compliance context.

## Orchestrator

The orchestrator classifies user intent and delegates:

- **Upload**: PDF attachment or pasted legislation text → Diff Agent first, then Indexing Agent
- **Question**: Legal/regulatory question → QA Agent
- **List**: "What documents are indexed?" → Direct graph query
- **Help**: Explain capabilities

Key instructions:
- Always explain what you're doing ("I'll check if this document is already indexed...")
- Never fabricate legal information
- Present sub-agent results in user-friendly format

## Indexing Agent

Follows a structured pipeline:
1. `extract_structure` → metadata, defined terms, cross-references
2. `chunk_legislation` → hierarchical article/paragraph chunks
3. `neo4j_write` → persist graph nodes and relationships
4. `vector_upsert` → generate and store embeddings
5. Report statistics (articles, paragraphs, cross-refs, terms)

## Diff Agent

Decision tree:
1. `compute_content_hash` on incoming document
2. `check_document_exists` with hash and short name
3. If identical → report "already indexed, no changes"
4. If different version → `diff_documents` for article-level comparison
5. Report: new/identical/updated with specific changes

## QA Agent

Citation format: `[Document Short Name, Art. X, Para. Y]`

Rules:
- Every factual claim gets a citation
- Never invent provisions not in search results
- Follow cross-references for completeness
- State explicitly when information is insufficient
- Distinguish between mandatory ("shall") and optional ("may") requirements

Retrieval strategy:
1. `hybrid_search` — vector + graph expansion (primary)
2. `get_article_with_context` — follow important cross-references
3. Synthesise answer with inline citations

## Updating Prompts

To modify agent behaviour:

1. Edit prompts in `src/fides/agents/prompts.py`
2. Run evaluation suite: `make eval`
3. Compare metrics against baseline
4. Commit when satisfied
