# Knowledge Graph Schema

This document describes the Neo4j knowledge graph schema used by Fides to
model legal documents, statutes, regulations, codes, and contracts from any jurisdiction.

## Design Principles

1. **Legislation-Native Hierarchy** — The graph preserves the official legal
   document structure (Title → Chapter → Section → Article → Paragraph, plus Annex and Recital),
   avoiding arbitrary token-slicing that destroys statutory context.

2. **Dual-Layer Architecture** — The structural backbone (document AST) is
   complemented by a dynamic semantic/normative layer (obligations, defined terms, actor roles,
   cross-references, and domain-specific entities) discovered at ingestion time.

3. **Dynamic Ontology Discovery** — Governed by the autonomous **Graph Builder Agent**,
   the semantic layer adapts dynamically to each ingested document without hardcoded jurisdiction assumptions.

4. **Merkle-Tree Content Hashing** — Every node carries a SHA-256 hash of its
   normalized text content, enabling instant change detection and targeted re-indexing.

5. **Multi-Index Reciprocal Rank Fusion (RRF)** — Articles, Paragraphs, Annexes, and Recitals
   carry dense vector embeddings (768 dimensions) and Lucene fulltext indexes, queried
   simultaneously using RRF score fusion (`1 / (60 + rank)`).

---

## Node Types

### 1. Structural Layer (Universal Legislative AST)

| Label | Key Properties | Description |
| :--- | :--- | :--- |
| `Document` | `id`, `title`, `short_name`, `document_type`, `publication_date`, `content_hash`, `indexed_at`, `version`, `eli_uri` | Root legal instrument (statute, regulation, code, contract) |
| `Chapter` | `id`, `number`, `title` | Major thematic division |
| `Section` | `id`, `number`, `title` | Sub-division within chapters |
| `Article` | `id`, `number`, `title`, `full_text`, `embedding`, `content_hash` | Core operational statutory unit |
| `Paragraph` | `id`, `number`, `text`, `embedding`, `content_hash` | Numbered provision within an article |
| `Annex` | `id`, `number`, `title`, `text`, `embedding` | Schedules, appendices, and procedural protocols |
| `Recital` | `id`, `number`, `text`, `embedding` | Preambles, legislative statements of purpose, and statutory intent |

### 2. Semantic & Normative Layer (Dynamic Discovery)

| Label | Key Properties | Description |
| :--- | :--- | :--- |
| `DefinedTerm` | `id`, `term`, `normalized_term`, `definition` | Legal definitions discovered from definitions provisions |
| `Obligation` | `id`, `modality` (`MUST`, `SHALL`, `MAY`, `PROHIBITED`), `description` | Operative compliance duties and legal requirements |
| `ActorRole` | `id`, `name` | Legal entities and regulated actors (e.g., `Manufacturer`, `Authorised Representative`, `Borrower`) |

---

## Relationship Types

### Structural Hierarchy
```cypher
(Document)-[:HAS_CHAPTER]->(Chapter)
(Document)-[:HAS_RECITAL]->(Recital)
(Document)-[:HAS_ANNEX]->(Annex)
(Chapter)-[:HAS_SECTION]->(Section)
(Chapter)-[:HAS_ARTICLE]->(Article)
(Section)-[:HAS_ARTICLE]->(Article)
(Article)-[:HAS_PARAGRAPH]->(Paragraph)
```

### Sequential Reading Order
```cypher
(Article)-[:NEXT_ARTICLE]->(Article)
(Paragraph)-[:NEXT_PARAGRAPH]->(Paragraph)
```

### Statutory Cross-References & Citations
```cypher
(Article)-[:CITES {ref_text: "..."}]->(Article)
(Article)-[:REFERENCES_ANNEX]->(Annex)
(Article)-[:INTERPRETED_BY]->(Recital)
(Article)-[:AMENDS]->(Article)
```

### Normative & Semantic Links
```cypher
(Article)-[:DEFINES]->(DefinedTerm)
(Paragraph)-[:USES_TERM]->(DefinedTerm)
(Paragraph)-[:IMPOSES]->(Obligation)
(Obligation)-[:APPLIES_TO]->(ActorRole)
(Obligation)-[:EXEMPTS_FROM]->(ActorRole)
```

---

## Indexes & Constraints

### Uniqueness Constraints
```cypher
CREATE CONSTRAINT document_id IF NOT EXISTS FOR (n:Document) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT recital_id IF NOT EXISTS FOR (n:Recital) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT chapter_id IF NOT EXISTS FOR (n:Chapter) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT section_id IF NOT EXISTS FOR (n:Section) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT article_id IF NOT EXISTS FOR (n:Article) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT paragraph_id IF NOT EXISTS FOR (n:Paragraph) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT annex_id IF NOT EXISTS FOR (n:Annex) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT term_id IF NOT EXISTS FOR (n:DefinedTerm) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT obligation_id IF NOT EXISTS FOR (n:Obligation) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT actor_role_id IF NOT EXISTS FOR (n:ActorRole) REQUIRE n.id IS UNIQUE;
```

### Fulltext Indexes
```cypher
CREATE FULLTEXT INDEX article_text IF NOT EXISTS FOR (n:Article) ON EACH [n.title, n.full_text];
CREATE FULLTEXT INDEX paragraph_text IF NOT EXISTS FOR (n:Paragraph) ON EACH [n.text];
CREATE FULLTEXT INDEX recital_text IF NOT EXISTS FOR (n:Recital) ON EACH [n.text];
CREATE FULLTEXT INDEX annex_text IF NOT EXISTS FOR (n:Annex) ON EACH [n.title, n.text];
```

### Vector Indexes (Cosine Similarity, 768 Dimensions)
```cypher
CREATE VECTOR INDEX vector_Article IF NOT EXISTS
  FOR (n:Article) ON (n.embedding)
  OPTIONS {indexConfig: {`vector.dimensions`: 768, `vector.similarity_function`: 'cosine'}};

CREATE VECTOR INDEX vector_Paragraph IF NOT EXISTS
  FOR (n:Paragraph) ON (n.embedding)
  OPTIONS {indexConfig: {`vector.dimensions`: 768, `vector.similarity_function`: 'cosine'}};

CREATE VECTOR INDEX vector_Recital IF NOT EXISTS
  FOR (n:Recital) ON (n.embedding)
  OPTIONS {indexConfig: {`vector.dimensions`: 768, `vector.similarity_function`: 'cosine'}};

CREATE VECTOR INDEX vector_Annex IF NOT EXISTS
  FOR (n:Annex) ON (n.embedding)
  OPTIONS {indexConfig: {`vector.dimensions`: 768, `vector.similarity_function`: 'cosine'}};
```

---

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
- `MDR:art:20` — Article 20 of the Medical Device Regulation
- `MDR:art:20:para:1` — Paragraph 1 of Article 20 (CE marking rule and custom-made exemption)
- `MDR:annex:XIII` — Annex XIII (Procedure for custom-made devices)
- `EU_AI_ACT:art:6:para:2` — Paragraph 2 of Article 6 of the EU AI Act

---

## Merkle-Tree Change Detection

Content hashes are computed bottom-up:
1. `hash(Paragraph) = SHA256(normalize(text))`
2. `hash(Article) = SHA256(title + sorted(paragraph_hashes))`
3. `hash(Document) = SHA256(sorted(article_hashes))`

During re-indexing:
- **Identical hash**: Skipped immediately with zero embedding or LLM cost.
- **Different hash**: Drills down to identify precisely which articles and paragraphs changed.
- Only changed provisions are updated in the graph and re-embedded.
