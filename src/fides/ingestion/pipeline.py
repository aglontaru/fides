"""
Central ingestion pipeline for legislation documents.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from neo4j import AsyncDriver

from fides.config.llm import create_embeddings
from fides.config.settings import FidesSettings, get_settings
from fides.graph.models import ArticleNode, DocumentNode, DocumentType, ParagraphNode, RecitalNode
from fides.graph.operations import (
    create_cross_reference,
    find_document_by_hash,
    find_document_by_name,
    get_document_chunks_manifest,
    link_article_references_annex,
    link_paragraph_uses_term,
    upsert_actor_role,
    upsert_annex,
    upsert_article,
    upsert_defined_term,
    upsert_document,
    upsert_obligation,
    upsert_ontology_schema,
    upsert_paragraph,
    upsert_recital,
)
from fides.ingestion.chunkers.legislation import LegislationChunker
from fides.ingestion.extractors.semantics import SemanticExtractor
from fides.ingestion.extractors.structure import StructureExtractor
from fides.ingestion.parsers.pdf import PDFParser

logger = structlog.get_logger(__name__)


class IngestionResult:
    """Result of an ingestion process."""

    def __init__(
        self,
        document_id: str,
        short_name: str,
        document_title: str,
        status: str,
        articles_count: int = 0,
        paragraphs_count: int = 0,
        recitals_count: int = 0,
        message: str = "",
    ) -> None:
        self.document_id = document_id
        self.short_name = short_name
        self.document_title = document_title
        self.status = status
        self.articles_count = articles_count
        self.paragraphs_count = paragraphs_count
        self.recitals_count = recitals_count
        self.message = message

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "short_name": self.short_name,
            "document_title": self.document_title,
            "status": self.status,
            "articles_count": self.articles_count,
            "paragraphs_count": self.paragraphs_count,
            "recitals_count": self.recitals_count,
            "message": self.message,
        }


class IngestionPipeline:
    """Orchestrates PDF parsing, chunking, graph persistence, and vector generation."""

    def __init__(
        self,
        driver: AsyncDriver,
        settings: FidesSettings | None = None,
    ) -> None:
        self.driver = driver
        self.settings = settings or get_settings()
        self.pdf_parser = PDFParser(batch_size=20)
        self.structure_extractor = StructureExtractor()

    async def ingest_pdf_bytes(
        self,
        content_bytes: bytes,
        filename: str,
        on_progress: Callable[[str], Any] | None = None,
    ) -> IngestionResult:
        """Ingest a PDF from raw bytes."""

        async def _progress(msg: str) -> None:
            if on_progress:
                res = on_progress(msg)
                if hasattr(res, "__await__"):
                    await res

        logger.info("Starting PDF ingestion", filename=filename, size=len(content_bytes))
        await _progress(f"Saving '{filename}' to storage...")

        # 1. Save file to disk
        storage_dir = Path(self.settings.document_storage_path)
        await asyncio.to_thread(storage_dir.mkdir, parents=True, exist_ok=True)
        file_path = storage_dir / filename
        await asyncio.to_thread(file_path.write_bytes, content_bytes)

        # 2. Compute full file hash
        content_hash = hashlib.sha256(content_bytes).hexdigest()
        existing_doc = await find_document_by_hash(self.driver, content_hash)
        if existing_doc:
            msg = f"Document '{existing_doc.short_name}' already indexed with identical content."
            logger.info("Document already exists", short_name=existing_doc.short_name)
            await _progress(msg)
            async with self.driver.session() as sess:
                c_res = await sess.run(
                    "MATCH (d:Document {id: $doc_id}) "
                    "OPTIONAL MATCH (d)-[:HAS_ARTICLE]->(a:Article) "
                    "OPTIONAL MATCH (d)-[:HAS_RECITAL]->(r:Recital) "
                    "OPTIONAL MATCH (a)-[:HAS_PARAGRAPH]->(p:Paragraph) "
                    "RETURN count(DISTINCT a) AS arts, count(DISTINCT r) AS recs, count(DISTINCT p) AS paras",
                    doc_id=existing_doc.id,
                )
                c_record = await c_res.single()
                e_arts = c_record["arts"] if c_record else 0
                e_recs = c_record["recs"] if c_record else 0
                e_paras = c_record["paras"] if c_record else 0

            return IngestionResult(
                document_id=existing_doc.id,
                short_name=existing_doc.short_name,
                document_title=existing_doc.title,
                status="identical",
                articles_count=e_arts,
                paragraphs_count=e_paras,
                recitals_count=e_recs,
                message=msg,
            )

        # 3. Parse PDF with PyMuPDF
        await _progress(f"Parsing '{filename}' with PyMuPDF...")
        parsed = await self.pdf_parser.parse(content_bytes, filename=filename)
        text = parsed.raw_text

        if not text.strip():
            err_msg = f"No text could be extracted from '{filename}'."
            logger.warning("Empty text extracted from PDF", filename=filename)
            await _progress(f"⚠️ {err_msg}")
            return IngestionResult(
                document_id=f"doc:{filename}",
                short_name=filename,
                document_title=filename,
                status="error",
                message=err_msg,
            )

        # 4. Extract Structure & Metadata
        await _progress("Analyzing legal structure & metadata...")
        structure = await self.structure_extractor.extract(text, filename=filename)
        short_name = structure.metadata.short_name
        doc_title = structure.metadata.title or filename
        doc_type_val = structure.metadata.document_type
        doc_type = DocumentType.REGULATION
        if doc_type_val == "directive":
            doc_type = DocumentType.DIRECTIVE
        elif doc_type_val == "decision":
            doc_type = DocumentType.DECISION

        doc_id = f"doc:{short_name}"

        # 5. Chunk the legislation into articles, recitals, and paragraphs
        await _progress(f"Chunking legislation hierarchy for '{short_name}'...")
        chunker = LegislationChunker(short_name=short_name, document_title=doc_title)
        chunked = await chunker.chunk(text)

        # 6. Check if this legislation already exists in the graph by short_name
        existing_doc = await find_document_by_name(self.driver, short_name)
        existing_manifest = (
            await get_document_chunks_manifest(self.driver, doc_id)
            if existing_doc
            else {"articles": {}, "paragraphs": {}, "recitals": {}}
        )

        doc_node = DocumentNode(
            id=doc_id,
            title=doc_title,
            short_name=short_name,
            document_type=doc_type,
            content_hash=content_hash,
            indexed_at=datetime.now(UTC),
        )
        await upsert_document(self.driver, doc_node)

        # 7. Generate embeddings and persist chunks
        embeddings_model = create_embeddings(self.settings)

        # Separate article, recital, and paragraph chunks
        articles_dict: dict[str, dict[str, Any]] = {}
        recitals_dict: dict[str, dict[str, Any]] = {}
        paragraphs_dict: dict[str, list[dict[str, Any]]] = {}

        for chunk in chunked.chunks:
            if chunk.chunk_type == "article":
                articles_dict[chunk.id] = {
                    "number": str(chunk.number),
                    "title": chunk.title or f"Article {chunk.number}",
                    "text": chunk.text,
                    "cross_references": chunk.cross_references,
                }
            elif chunk.chunk_type == "recital":
                recitals_dict[chunk.id] = {
                    "number": str(chunk.number),
                    "title": chunk.title or f"Recital ({chunk.number})",
                    "text": chunk.text,
                }
            elif chunk.chunk_type == "paragraph":
                art_id = chunk.parent_id or (
                    chunk.id.rsplit(":para:", 1)[0] if ":para:" in chunk.id else ""
                )
                if art_id not in paragraphs_dict:
                    paragraphs_dict[art_id] = []
                paragraphs_dict[art_id].append(
                    {
                        "id": chunk.id,
                        "number": str(chunk.number),
                        "text": chunk.text,
                    }
                )

        total_articles = len(articles_dict)
        total_recitals = len(recitals_dict)
        total_paras = sum(len(p_list) for p_list in paragraphs_dict.values())
        await _progress(
            f"Found {total_articles} articles, {total_recitals} recitals, and {total_paras} paragraphs. Writing to Neo4j..."
        )

        # Upsert recitals with change detection
        indexed_recitals = 0
        recitals_unchanged = 0
        recitals_updated = 0
        recitals_added = 0

        for rec_id, rec_data in recitals_dict.items():
            rec_text = rec_data["text"]
            # Check if identical recital already exists in graph
            if (
                rec_id in existing_manifest["recitals"]
                and existing_manifest["recitals"][rec_id] == rec_text
            ):
                recitals_unchanged += 1
                indexed_recitals += 1
                continue

            is_new = rec_id not in existing_manifest["recitals"]
            rec_emb: list[float] | None = None
            try:
                rec_emb = await embeddings_model.aembed_query(rec_text[:4000])
            except Exception as emb_err:
                logger.warning("Failed embedding for recital", rec_id=rec_id, error=str(emb_err))

            recital_node = RecitalNode(
                id=rec_id,
                number=rec_data["number"],
                text=rec_text,
                embedding=rec_emb,
            )
            await upsert_recital(self.driver, doc_id=doc_id, recital=recital_node)
            if is_new:
                recitals_added += 1
            else:
                recitals_updated += 1
            indexed_recitals += 1
            if indexed_recitals % 5 == 0 or indexed_recitals == total_recitals:
                await _progress(
                    f"Indexed {indexed_recitals}/{total_recitals} recitals into graph..."
                )

        # Upsert articles and paragraphs with change detection
        indexed_articles = 0
        indexed_paras = 0
        articles_unchanged = 0
        articles_updated = 0
        articles_added = 0
        paras_unchanged = 0
        paras_updated = 0
        paras_added = 0

        for art_id, art_data in articles_dict.items():
            art_text = art_data["text"]
            art_hash = hashlib.sha256(art_text.encode("utf-8")).hexdigest()
            art_paras = paragraphs_dict.get(art_id, [])

            art_in_graph = art_id in existing_manifest["articles"]
            art_is_unchanged = art_in_graph and existing_manifest["articles"][art_id] == art_hash

            if art_is_unchanged:
                articles_unchanged += 1
                indexed_articles += 1
                # Check paragraphs
                for p in art_paras:
                    p_text = p["text"]
                    p_hash = hashlib.sha256(p_text.encode("utf-8")).hexdigest()
                    if (
                        p["id"] in existing_manifest["paragraphs"]
                        and existing_manifest["paragraphs"][p["id"]] == p_hash
                    ):
                        paras_unchanged += 1
                        indexed_paras += 1
                    else:
                        p_emb = None
                        try:
                            p_emb = await embeddings_model.aembed_query(p_text)
                        except Exception as emb_err:
                            logger.warning(
                                "Failed embedding for paragraph", p_id=p["id"], error=str(emb_err)
                            )
                        para_node = ParagraphNode(
                            id=p["id"],
                            number=p["number"],
                            text=p_text,
                            content_hash=p_hash,
                            embedding=p_emb,
                        )
                        await upsert_paragraph(self.driver, article_id=art_id, para=para_node)
                        if p["id"] in existing_manifest["paragraphs"]:
                            paras_updated += 1
                        else:
                            paras_added += 1
                        indexed_paras += 1
            else:
                # Article is new or modified
                art_emb: list[float] | None = None
                try:
                    art_emb = await embeddings_model.aembed_query(art_text[:4000])
                except Exception as emb_err:
                    logger.warning(
                        "Failed embedding for article", art_id=art_id, error=str(emb_err)
                    )

                article_node = ArticleNode(
                    id=art_id,
                    number=art_data["number"],
                    title=art_data["title"],
                    full_text=art_text,
                    content_hash=art_hash,
                    embedding=art_emb,
                )
                await upsert_article(self.driver, doc_id=doc_id, article=article_node)
                if art_in_graph:
                    articles_updated += 1
                else:
                    articles_added += 1
                indexed_articles += 1

                # Process paragraphs for this article
                for p in art_paras:
                    p_text = p["text"]
                    p_hash = hashlib.sha256(p_text.encode("utf-8")).hexdigest()
                    p_in_graph = p["id"] in existing_manifest["paragraphs"]
                    if p_in_graph and existing_manifest["paragraphs"][p["id"]] == p_hash:
                        paras_unchanged += 1
                        indexed_paras += 1
                        continue

                    p_emb = None
                    try:
                        p_emb = await embeddings_model.aembed_query(p_text)
                    except Exception as emb_err:
                        logger.warning(
                            "Failed embedding for paragraph", p_id=p["id"], error=str(emb_err)
                        )

                    para_node = ParagraphNode(
                        id=p["id"],
                        number=p["number"],
                        text=p_text,
                        content_hash=p_hash,
                        embedding=p_emb,
                    )
                    await upsert_paragraph(self.driver, article_id=art_id, para=para_node)
                    if p_in_graph:
                        paras_updated += 1
                    else:
                        paras_added += 1
                    indexed_paras += 1

            # Cross references
            for ref_id in art_data.get("cross_references", []):
                try:
                    await create_cross_reference(self.driver, from_id=art_id, to_id=ref_id)
                except Exception as ref_err:
                    logger.debug(
                        "Cross-ref link skipped", from_id=art_id, to_id=ref_id, error=str(ref_err)
                    )

            if indexed_articles % 5 == 0 or indexed_articles == total_articles:
                await _progress(
                    f"Processed {indexed_articles}/{total_articles} articles into graph..."
                )

        # 8. Semantic Entity & Relationship Extraction
        await _progress("Extracting semantic entities (DefinedTerms, Obligations, ActorRoles)...")
        sem_extractor = SemanticExtractor(short_name=short_name)
        sem_result = sem_extractor.extract(chunked.chunks)

        for role in sem_result.actor_roles:
            try:
                await upsert_actor_role(self.driver, role)
            except Exception as e:
                logger.debug("ActorRole upsert skipped", role=role.name, error=str(e))

        for annex in sem_result.annex_nodes:
            try:
                annex_emb: list[float] | None = None
                try:
                    annex_content = f"{annex.title}\n\n{annex.text[:4000]}"
                    annex_emb = await embeddings_model.aembed_query(annex_content)
                except Exception as emb_e:
                    logger.debug("Annex embedding skipped", annex_id=annex.id, error=str(emb_e))
                annex.embedding = annex_emb
                await upsert_annex(self.driver, doc_id=doc_id, annex=annex)
            except Exception as e:
                logger.debug("Annex upsert skipped", annex_id=annex.id, error=str(e))

        for term in sem_result.defined_terms:
            try:
                def_art = next(
                    (art_id for art_id, t_id in sem_result.article_defines if t_id == term.id),
                    None,
                )
                if def_art:
                    await upsert_defined_term(self.driver, article_id=def_art, term=term)
            except Exception as e:
                logger.debug("DefinedTerm upsert skipped", term=term.term, error=str(e))

        for para_id, term_id in sem_result.paragraph_uses_term:
            try:
                await link_paragraph_uses_term(self.driver, paragraph_id=para_id, term_id=term_id)
            except Exception as e:
                logger.debug("USES_TERM link skipped", para_id=para_id, term_id=term_id, error=str(e))

        obl_role_map = dict(sem_result.obligation_applies_to)
        for obl in sem_result.obligations:
            try:
                imposing_art = next(
                    (art_id for art_id, o_id in sem_result.article_imposes if o_id == obl.id),
                    None,
                )
                if imposing_art:
                    target_role = obl_role_map.get(obl.id)
                    await upsert_obligation(
                        self.driver,
                        article_id=imposing_art,
                        obligation=obl,
                        actor_role_name=target_role,
                    )
            except Exception as e:
                logger.debug("Obligation upsert skipped", obl_id=obl.id, error=str(e))

        for art_id, annex_id in sem_result.article_references_annex:
            try:
                await link_article_references_annex(self.driver, article_id=art_id, annex_id=annex_id)
            except Exception as e:
                logger.debug("REFERENCES_ANNEX link skipped", art_id=art_id, annex_id=annex_id, error=str(e))

        if sem_result.schema_record:
            try:
                await upsert_ontology_schema(
                    self.driver,
                    document_id=doc_id,
                    domain=sem_result.schema_record.domain,
                    node_types=sem_result.schema_record.node_types,
                    relationship_types=sem_result.schema_record.relationship_types,
                    description=sem_result.schema_record.description,
                )
            except Exception as e:
                logger.debug("OntologySchema upsert skipped", doc_id=doc_id, error=str(e))

        if existing_doc:
            diff_parts = []
            if articles_updated or articles_added:
                diff_parts.append(
                    f"{articles_updated} articles modified, {articles_added} articles added, {articles_unchanged} unchanged"
                )
            if recitals_updated or recitals_added:
                diff_parts.append(
                    f"{recitals_updated} recitals modified, {recitals_added} recitals added, {recitals_unchanged} unchanged"
                )
            diff_str = "; ".join(diff_parts) if diff_parts else "All provisions were unchanged"
            final_msg = f"Updated '{short_name}': {diff_str}."
        else:
            final_msg = (
                f"Successfully indexed '{short_name}': {indexed_articles} articles, "
                f"{indexed_recitals} recitals, {indexed_paras} paragraphs with vector embeddings."
            )
        logger.info("Ingestion completed successfully", doc_id=doc_id, short_name=short_name)
        await _progress(final_msg)

        return IngestionResult(
            document_id=doc_id,
            short_name=short_name,
            document_title=doc_title,
            status="updated_document" if existing_doc else "new_document",
            articles_count=indexed_articles,
            paragraphs_count=indexed_paras,
            recitals_count=indexed_recitals,
            message=final_msg,
        )
