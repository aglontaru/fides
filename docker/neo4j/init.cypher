// Neo4j initialization script with constraints and indexes for Fides
// Synchronized with src/fides/graph/schema.py

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

CREATE INDEX document_hash IF NOT EXISTS FOR (n:Document) ON (n.content_hash);
CREATE INDEX document_short_name IF NOT EXISTS FOR (n:Document) ON (n.short_name);

CREATE FULLTEXT INDEX article_text IF NOT EXISTS FOR (n:Article) ON EACH [n.title, n.full_text];
CREATE FULLTEXT INDEX paragraph_text IF NOT EXISTS FOR (n:Paragraph) ON EACH [n.text];
CREATE FULLTEXT INDEX recital_text IF NOT EXISTS FOR (n:Recital) ON EACH [n.text];
CREATE FULLTEXT INDEX annex_text IF NOT EXISTS FOR (n:Annex) ON EACH [n.title, n.text];
