"""
FastAPI application for Fides.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, UploadFile, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from fides.api.schemas import DocumentUploadResponse, SystemStatus
from fides.api.websocket import handle_websocket
from fides.config.settings import get_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan context manager for startup and shutdown events."""
    logger.info("Starting up Fides API")
    settings = get_settings()
    try:
        from neo4j import AsyncGraphDatabase

        from fides.graph.schema import initialize_schema

        driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
        )
        await initialize_schema(driver, embedding_dimensions=settings.embedding_dimensions)
        await driver.close()
        logger.info("Neo4j schema and vector indexes initialized successfully")
    except Exception as e:
        logger.warning(f"Could not auto-initialize Neo4j schema on startup: {e}")

    yield
    logger.info("Shutting down Fides API")


app = FastAPI(title="Fides API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=SystemStatus)
async def health_check() -> SystemStatus:
    """Health check endpoint."""
    settings = get_settings()
    doc_count = 0
    neo4j_ok = False
    try:
        from neo4j import AsyncGraphDatabase

        driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
        )
        async with driver.session() as session:
            res = await session.run("MATCH (d:Document) RETURN count(d) AS count")
            rec = await res.single()
            if rec:
                doc_count = rec["count"]
                neo4j_ok = True
        await driver.close()
    except Exception:
        neo4j_ok = False

    return SystemStatus(
        status="healthy" if neo4j_ok else "degraded",
        neo4j_connected=neo4j_ok,
        mcp_server_connected=True,
        llm_provider=settings.llm_provider.value,
        indexed_documents=doc_count,
    )


@app.get("/api/documents")
async def list_documents() -> list[dict[str, Any]]:
    """List indexed documents."""
    settings = get_settings()
    try:
        from neo4j import AsyncGraphDatabase

        driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
        )
        async with driver.session() as session:
            res = await session.run(
                "MATCH (d:Document) "
                "OPTIONAL MATCH (d)-[:HAS_ARTICLE]->(a:Article) "
                "OPTIONAL MATCH (d)-[:HAS_RECITAL]->(r:Recital) "
                "RETURN d.id AS id, d.title AS title, d.short_name AS short_name, "
                "count(DISTINCT a) AS articles, count(DISTINCT r) AS recitals "
                "ORDER BY d.short_name"
            )
            records = [record.data() async for record in res]
        await driver.close()
        return records
    except Exception as e:
        logger.error(f"Failed to list documents: {e}")
        return []


@app.delete("/api/documents/{document_id}")
async def delete_document(document_id: str) -> dict[str, Any]:
    """Delete a document and all its descendant nodes/vectors from the knowledge graph."""
    settings = get_settings()
    try:
        from neo4j import AsyncGraphDatabase

        from fides.graph.operations import delete_document_graph

        driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
        )
        deleted_count = await delete_document_graph(driver, document_id)
        await driver.close()

        logger.info(f"Deleted document '{document_id}' from graph, removed {deleted_count} nodes")
        return {
            "status": "deleted",
            "document_id": document_id,
            "deleted_nodes": deleted_count,
        }
    except Exception as e:
        logger.error(f"Failed to delete document {document_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/documents/upload", response_model=DocumentUploadResponse)
async def upload_document(file: UploadFile) -> DocumentUploadResponse:
    """Upload PDF via REST."""
    settings = get_settings()
    try:
        from neo4j import AsyncGraphDatabase

        from fides.ingestion import IngestionPipeline

        content_bytes = await file.read()
        driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
        )
        try:
            pipeline = IngestionPipeline(driver=driver, settings=settings)
            result = await pipeline.ingest_pdf_bytes(
                content_bytes=content_bytes,
                filename=file.filename or "uploaded.pdf",
            )
        finally:
            await driver.close()

        return DocumentUploadResponse(
            status=result.status,
            document_title=result.document_title,
            details=result.message
            or f"Indexed {result.articles_count} articles and {result.recitals_count} recitals.",
            articles_indexed=result.articles_count,
        )
    except Exception as e:
        logger.error(f"REST upload failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.websocket("/ws/chat")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket chat endpoint."""
    await handle_websocket(websocket)


# Serve static files last
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def root() -> FileResponse:
    """Serve the chat UI."""
    return FileResponse(os.path.join(static_dir, "index.html"))


def main() -> None:
    """Entry point to run the API server."""
    settings = get_settings()
    uvicorn.run(
        "fides.api.main:app",
        host=settings.fides_api_host,
        port=settings.fides_api_port,
        reload=True,
    )


if __name__ == "__main__":
    main()
