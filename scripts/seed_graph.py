"""Seed Neo4j with a sample legislation excerpt for development and testing.

Usage:
    uv run python scripts/seed_graph.py

This script inserts a small excerpt of the EU AI Act into the knowledge graph,
including articles, paragraphs, recitals, defined terms, and cross-references.
It is intended for local development and demo purposes.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import sys

# Ensure the project source is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def _hash(text: str) -> str:
    """Compute SHA-256 hash of normalised text."""
    return hashlib.sha256(text.strip().lower().encode()).hexdigest()


# ---------------------------------------------------------------------------
# Sample EU AI Act data (simplified excerpt)
# ---------------------------------------------------------------------------

DOCUMENT = {
    "id": "EU_AI_ACT_2024_1689",
    "title": "Regulation (EU) 2024/1689 of the European Parliament and of the Council "
    "laying down harmonised rules on artificial intelligence (Artificial Intelligence Act)",
    "short_name": "EU AI Act",
    "document_type": "regulation",
    "publication_date": "2024-07-12",
    "eli_uri": "http://data.europa.eu/eli/reg/2024/1689/oj",
    "version": "2024-07-12",
}

RECITALS = [
    {
        "number": 1,
        "text": (
            "The purpose of this Regulation is to improve the functioning of the internal "
            "market by laying down a uniform legal framework in particular for the development, "
            "the placing on the market, the putting into service and the use of artificial "
            "intelligence systems in the Union."
        ),
    },
    {
        "number": 6,
        "text": (
            "The notion of AI system in this Regulation should be clearly defined and should "
            "be closely aligned with the work of international organisations working on "
            "artificial intelligence."
        ),
    },
    {
        "number": 47,
        "text": (
            "High-risk AI systems should only be placed on the Union market, put into service "
            "or used if they comply with certain mandatory requirements."
        ),
    },
]

ARTICLES = [
    {
        "number": 1,
        "title": "Subject matter",
        "paragraphs": [
            {
                "number": 1,
                "text": (
                    "The purpose of this Regulation is to improve the functioning of the "
                    "internal market and promote the uptake of human-centric and trustworthy "
                    "artificial intelligence (AI), while ensuring a high level of protection "
                    "of health, safety, fundamental rights enshrined in the Charter, including "
                    "democracy, the rule of law and environmental protection, against the "
                    "harmful effects of artificial intelligence systems ('AI systems') in the "
                    "Union, and to support innovation."
                ),
            },
            {
                "number": 2,
                "text": (
                    "This Regulation lays down: (a) harmonised rules for the placing on the "
                    "market, the putting into service and the use of AI systems in the Union; "
                    "(b) prohibitions of certain artificial intelligence practices; "
                    "(c) specific requirements for high-risk AI systems and obligations for "
                    "operators of such systems; (d) harmonised transparency rules for certain "
                    "AI systems; (e) harmonised rules for the placing on the market of "
                    "general-purpose AI models; (f) rules on market monitoring, market "
                    "surveillance, governance and enforcement; (g) measures to support innovation."
                ),
            },
        ],
    },
    {
        "number": 3,
        "title": "Definitions",
        "paragraphs": [
            {
                "number": 1,
                "text": (
                    "For the purposes of this Regulation, the following definitions apply: "
                    "(1) 'AI system' means a machine-based system that is designed to operate "
                    "with varying levels of autonomy, that may exhibit adaptiveness after "
                    "deployment and that, for explicit or implicit objectives, infers, from the "
                    "input it receives, how to generate outputs such as predictions, content, "
                    "recommendations, or decisions that can influence physical or virtual "
                    "environments;"
                ),
            },
        ],
        "defined_terms": [
            {
                "term": "AI system",
                "definition": (
                    "a machine-based system that is designed to operate with varying levels "
                    "of autonomy, that may exhibit adaptiveness after deployment and that, "
                    "for explicit or implicit objectives, infers, from the input it receives, "
                    "how to generate outputs such as predictions, content, recommendations, "
                    "or decisions that can influence physical or virtual environments"
                ),
            },
            {
                "term": "provider",
                "definition": (
                    "a natural or legal person, public authority, agency or other body that "
                    "develops an AI system or a general-purpose AI model or that has an AI "
                    "system or a general-purpose AI model developed and places it on the "
                    "market or puts the AI system into service under its own name or trademark"
                ),
            },
            {
                "term": "deployer",
                "definition": (
                    "a natural or legal person, public authority, agency or other body using "
                    "an AI system under its authority except where the AI system is used in "
                    "the course of a personal non-professional activity"
                ),
            },
        ],
    },
    {
        "number": 5,
        "title": "Prohibited artificial intelligence practices",
        "paragraphs": [
            {
                "number": 1,
                "text": (
                    "The following artificial intelligence practices shall be prohibited: "
                    "(a) the placing on the market, the putting into service or the use of an "
                    "AI system that deploys subliminal techniques beyond a person's "
                    "consciousness or purposefully manipulative or deceptive techniques, with "
                    "the objective or the effect of materially distorting the behaviour of a "
                    "person or a group of persons;"
                ),
            },
        ],
    },
    {
        "number": 6,
        "title": "Classification rules for high-risk AI systems",
        "paragraphs": [
            {
                "number": 1,
                "text": (
                    "Irrespective of whether an AI system is placed on the market or put into "
                    "service independently of the products referred to in points (a) and (b), "
                    "that AI system shall be considered to be high-risk where both of the "
                    "following conditions are fulfilled: (a) the AI system is intended to be "
                    "used as a safety component of a product, or the AI system is itself a "
                    "product, covered by the Union harmonisation legislation listed in Annex I; "
                    "(b) the product whose safety component pursuant to point (a) is the AI "
                    "system, or the AI system itself as a product, is required to undergo a "
                    "third-party conformity assessment."
                ),
            },
            {
                "number": 2,
                "text": (
                    "In addition to the high-risk AI systems referred to in paragraph 1, AI "
                    "systems referred to in Annex III shall be considered to be high-risk."
                ),
            },
        ],
        "cross_refs": ["EU_AI_ACT_2024_1689:art:1", "EU_AI_ACT_2024_1689:annex:1"],
    },
    {
        "number": 16,
        "title": "Obligations of providers of high-risk AI systems",
        "paragraphs": [
            {
                "number": 1,
                "text": (
                    "Providers of high-risk AI systems shall: (a) ensure that their high-risk "
                    "AI systems are compliant with the requirements set out in Chapter III, "
                    "Section 2; (b) indicate on the high-risk AI system or, where that is not "
                    "possible, on its packaging or its accompanying documentation, as "
                    "applicable, their name, registered trade name or registered trade mark, "
                    "the address at which they can be contacted;"
                ),
            },
        ],
        "cross_refs": ["EU_AI_ACT_2024_1689:art:6"],
    },
]


async def seed() -> None:
    """Seed the Neo4j database with sample EU AI Act data."""
    from neo4j import AsyncGraphDatabase

    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "fides-dev-password")

    print(f"Connecting to Neo4j at {uri}...")
    driver = AsyncGraphDatabase.driver(uri, auth=(user, password))

    try:
        # Verify connectivity
        async with driver.session() as session:
            result = await session.run("RETURN 1 AS n")
            await result.single()
        print("✓ Connected to Neo4j")

        # Initialize schema
        from fides.graph.schema import initialize_schema

        await initialize_schema(driver)
        print("✓ Schema initialized")

        # Insert document
        doc_hash = _hash(str(ARTICLES))
        async with driver.session() as session:
            await session.run(
                """
                MERGE (d:Document {id: $id})
                SET d.title = $title,
                    d.short_name = $short_name,
                    d.document_type = $document_type,
                    d.publication_date = date($publication_date),
                    d.eli_uri = $eli_uri,
                    d.version = $version,
                    d.content_hash = $content_hash,
                    d.indexed_at = datetime()
                """,
                {**DOCUMENT, "content_hash": doc_hash},
            )
        print(f"✓ Document: {DOCUMENT['short_name']}")

        # Insert recitals
        async with driver.session() as session:
            for rec in RECITALS:
                rec_id = f"{DOCUMENT['id']}:recital:{rec['number']}"
                await session.run(
                    """
                    MATCH (d:Document {id: $doc_id})
                    MERGE (r:Recital {id: $rec_id})
                    SET r.number = $number, r.text = $text
                    MERGE (d)-[:HAS_RECITAL]->(r)
                    """,
                    {
                        "doc_id": DOCUMENT["id"],
                        "rec_id": rec_id,
                        "number": rec["number"],
                        "text": rec["text"],
                    },
                )
            print(f"✓ Recitals: {len(RECITALS)}")

        # Insert articles and paragraphs
        async with driver.session() as session:
            for art in ARTICLES:
                art_id = f"{DOCUMENT['id']}:art:{art['number']}"
                art_hash = _hash(str(art))
                await session.run(
                    """
                    MATCH (d:Document {id: $doc_id})
                    MERGE (a:Article {id: $art_id})
                    SET a.number = $number,
                        a.title = $title,
                        a.content_hash = $art_hash
                    MERGE (d)-[:HAS_ARTICLE]->(a)
                    """,
                    {
                        "doc_id": DOCUMENT["id"],
                        "art_id": art_id,
                        "number": art["number"],
                        "title": art["title"],
                        "art_hash": art_hash,
                    },
                )

                # Paragraphs
                for para in art["paragraphs"]:
                    para_id = f"{art_id}:para:{para['number']}"
                    para_hash = _hash(para["text"])
                    await session.run(
                        """
                        MATCH (a:Article {id: $art_id})
                        MERGE (p:Paragraph {id: $para_id})
                        SET p.number = $number,
                            p.text = $text,
                            p.content_hash = $para_hash
                        MERGE (a)-[:HAS_PARAGRAPH]->(p)
                        """,
                        {
                            "art_id": art_id,
                            "para_id": para_id,
                            "number": para["number"],
                            "text": para["text"],
                            "para_hash": para_hash,
                        },
                    )

                # Defined terms
                for term in art.get("defined_terms", []):
                    normalized = term["term"].strip().lower()
                    await session.run(
                        """
                        MATCH (a:Article {id: $art_id})
                        MERGE (t:DefinedTerm {normalized_term: $normalized})
                        SET t.term = $term, t.definition = $definition
                        MERGE (a)-[:DEFINES]->(t)
                        """,
                        {
                            "art_id": art_id,
                            "normalized": normalized,
                            "term": term["term"],
                            "definition": term["definition"],
                        },
                    )

                # Cross-references
                for ref in art.get("cross_refs", []):
                    await session.run(
                        """
                        MATCH (a:Article {id: $art_id})
                        MERGE (target {id: $target_id})
                        MERGE (a)-[:CITES]->(target)
                        """,
                        {"art_id": art_id, "target_id": ref},
                    )

                print(f"  ✓ Article {art['number']}: {art['title']}")

        # Summary
        async with driver.session() as session:
            result = await session.run(
                "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count "
                "ORDER BY count DESC"
            )
            records = [r async for r in result]
            print("\n── Graph Summary ──")
            for record in records:
                print(f"  {record['label']}: {record['count']}")

        print("\n✓ Seed complete!")

    finally:
        await driver.close()


if __name__ == "__main__":
    asyncio.run(seed())
