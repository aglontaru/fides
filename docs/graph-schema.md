# Knowledge Graph Schema

This document describes the Neo4j knowledge graph schema used by Fides to
model EU legislation documents.

## Design Principles

1. **Legislation-native hierarchy** — The graph follows the official legal
   document structure (Title → Chapter → Section → Article → Paragraph),
   not arbitrary token-based chunks.

2. **Dual-layer architecture** — Structural backbone (document AST) is
   separated from semantic/normative layer (obligations, defined terms,
   cross-references).

3. **Content hashing for dedup** — Every node carries a SHA-256 hash of its
   normalised text content. This enables Merkle-tree-style change detection
   during re-indexing.

4. **Embedded vectors for RAG** — Article and Paragraph nodes carry vector
   embeddings for semantic similarity search via Neo4j Vector Index.

## Node Types

### Document Structure (Lexical Layer)

| Label | Key Properties | Description |
|-------|---------------|-------------|
| `Document` | `id`, `title`, `short_name`, `document_type`, `publication_date`, `content_hash`, `indexed_at`, `version`, `eli_uri` | Top-level regulation |
| `Recital` | `id`, `number`, `text`, `embedding` | Preamble items stating legislative intent |
| `Chapter` | `id`, `number`, `title` | Thematic grouping |
| `Section` | `id`, `number`, `title` | Sub-division within chapters |
| `Article` | `id`, `number`, `title`, `full_text`, `embedding`, `content_hash` | Core operational unit |
| `Paragraph` | `id`, `number`, `text`, `embedding`, `content_hash` | Numbered paragraph within an article |
| `Annex` | `id`, `number`, `title`, `text`, `embedding` | Appendices |

### Semantic Layer

| Label | Key Properties | Description |
|-------|---------------|-------------|
| `DefinedTerm` | `id`, `term`, `normalized_term`, `definition` | Legal definitions (typically Art. 2-3) |
| `Obligation` | `id`, `modality`, `description` | Compliance duties ("shall", "must") |
| `ActorRole` | `id`, `name` | Regulated entities ("Provider", "Deployer") |

## Relationship Types

### Structural Relationships

```cypher
(Document)-[:HAS_CHAPTER]->(Chapter)
(Document)-[:HAS_RECITAL]->(Recital)
(Document)-[:HAS_ANNEX]->(Annex)
(Chapter)-[:HAS_SECTION]->(Section)
(Chapter)-[:HAS_ARTICLE]->(Article)       // Direct, when no sections
(Section)-[:HAS_ARTICLE]->(Article)
(Article)-[:HAS_PARAGRAPH]->(Paragraph)
```

### Reading Order

```cypher
(Article)-[:NEXT_ARTICLE]->(Article)
(Paragraph)-[:NEXT_PARAGRAPH]->(Paragraph)
```

### Cross-References

```cypher
(Article)-[:CITES {ref_text: "..."}]->(Article)
(Article)-[:REFERENCES_ANNEX]->(Annex)
(Article)-[:INTERPRETED_BY]->(Recital)
(Article)-[:AMENDS]->(Article)             // Cross-regulation
```

### Normative Relationships

```cypher
(Article)-[:DEFINES]->(DefinedTerm)
(Paragraph)-[:USES_TERM]->(DefinedTerm)
(Paragraph)-[:IMPOSES]->(Obligation)
(Obligation)-[:APPLIES_TO]->(ActorRole)
```

## Indexes

### Constraints (Uniqueness)

```cypher
CREATE CONSTRAINT FOR (d:Document) REQUIRE d.id IS UNIQUE;
CREATE CONSTRAINT FOR (a:Article) REQUIRE a.id IS UNIQUE;
CREATE CONSTRAINT FOR (p:Paragraph) REQUIRE p.id IS UNIQUE;
CREATE CONSTRAINT FOR (r:Recital) REQUIRE r.id IS UNIQUE;
CREATE CONSTRAINT FOR (x:Annex) REQUIRE x.id IS UNIQUE;
CREATE CONSTRAINT FOR (t:DefinedTerm) REQUIRE t.normalized_term IS UNIQUE;
```

### Fulltext Indexes

```cypher
CREATE FULLTEXT INDEX article_fulltext
  FOR (a:Article) ON EACH [a.title, a.full_text];

CREATE FULLTEXT INDEX paragraph_fulltext
  FOR (p:Paragraph) ON EACH [p.text];
```

### Vector Indexes

```cypher
CREATE VECTOR INDEX paragraph_embeddings
  FOR (p:Paragraph) ON (p.embedding)
  OPTIONS {indexConfig: {
    `vector.dimensions`: 768,
    `vector.similarity_function`: 'cosine'
  }};

CREATE VECTOR INDEX recital_embeddings
  FOR (r:Recital) ON (r.embedding)
  OPTIONS {indexConfig: {
    `vector.dimensions`: 768,
    `vector.similarity_function`: 'cosine'
  }};
```

## ID Conventions

Node IDs follow a deterministic hierarchical pattern:

```
Document:  {short_name}
Chapter:   {short_name}:chapter:{number}
Section:   {short_name}:chapter:{c}:section:{number}
Article:   {short_name}:art:{number}
Paragraph: {short_name}:art:{a}:para:{number}
Recital:   {short_name}:recital:{number}
Annex:     {short_name}:annex:{number}
```

Examples:
- `EU_AI_ACT_2024_1689:art:6` — Article 6 of the EU AI Act
- `EU_AI_ACT_2024_1689:art:6:para:2` — Paragraph 2 of Article 6
- `EU_AI_ACT_2024_1689:recital:47` — Recital 47

## Change Detection (Merkle Hashing)

Content hashes are computed bottom-up:

1. `hash(Paragraph) = SHA256(normalize(text))`
2. `hash(Article) = SHA256(title + sorted(paragraph_hashes))`
3. `hash(Document) = SHA256(sorted(article_hashes))`

During re-indexing:
- **Same hash** → skip (no re-embedding, no LLM cost)
- **Different hash** → drill down to find changed paragraphs
- Only changed nodes get new embeddings and updated relationships
