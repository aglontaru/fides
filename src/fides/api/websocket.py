import base64
import json
import logging
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from langchain_core.messages import AIMessage

from fides.agents.factory import AgentSystem, create_agent_system
from fides.config.settings import get_settings

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []
        self._agent_systems: dict[WebSocket, AgentSystem] = {}

    async def connect(self, websocket: WebSocket) -> AgentSystem:
        await websocket.accept()
        self.active_connections.append(websocket)
        settings = get_settings()
        agent_system = await create_agent_system(settings)
        self._agent_systems[websocket] = agent_system
        return agent_system

    async def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        if websocket in self._agent_systems:
            agent_system = self._agent_systems.pop(websocket)
            await agent_system.close()

    async def send_message(self, message: dict[str, Any], websocket: WebSocket) -> None:
        await websocket.send_text(json.dumps(message))

    async def send_error(self, message: str, websocket: WebSocket) -> None:
        await self.send_message({"type": "error", "content": message}, websocket)


manager = ConnectionManager()




async def handle_websocket(websocket: WebSocket) -> None:
    """Handle incoming WebSocket connection and dispatch to the AgentSystem."""
    agent_system = await manager.connect(websocket)
    try:
        # Welcome message
        await manager.send_message(
            {
                "type": "message",
                "content": (
                    "👋 **Connected to Fides Knowledge Graph System.**\n"
                    "You can ask regulatory questions or upload a legislation PDF."
                ),
            },
            websocket,
        )

        while True:
            raw_data = await websocket.receive_text()
            try:
                payload = json.loads(raw_data)
            except json.JSONDecodeError:
                payload = {"type": "text", "content": raw_data}

            msg_type = payload.get("type", "text")

            if msg_type == "upload":
                filename = payload.get("filename", "uploaded_document.pdf")
                file_b64 = payload.get("content_base64", "")
                if not file_b64:
                    await manager.send_error("No file content received.", websocket)
                    continue

                try:
                    content_bytes = base64.b64decode(file_b64)
                except Exception as b64_err:
                    await manager.send_error(f"Failed to decode base64 file: {b64_err}", websocket)
                    continue

                # Progress callback to stream status updates directly to WebSocket
                async def progress_callback(status_text: str) -> None:
                    await manager.send_message(
                        {"type": "status", "content": status_text},
                        websocket,
                    )

                try:
                    settings = get_settings()
                    from neo4j import AsyncGraphDatabase

                    from fides.ingestion.pipeline import IngestionPipeline

                    neo4j_driver = AsyncGraphDatabase.driver(
                        settings.neo4j_uri,
                        auth=(
                            settings.neo4j_user,
                            settings.neo4j_password.get_secret_value(),
                        ),
                    )
                    pipeline = IngestionPipeline(driver=neo4j_driver, settings=settings)
                    ingest_result = await pipeline.ingest_pdf_bytes(
                        content_bytes=content_bytes,
                        filename=filename,
                        on_progress=progress_callback,
                    )
                    await neo4j_driver.close()

                    # Provide feedback to the user and notify orchestrator
                    short_name = ingest_result.short_name
                    doc_title = ingest_result.document_title
                    art_count = ingest_result.articles_count
                    rec_count = ingest_result.recitals_count
                    para_count = ingest_result.paragraphs_count

                    stat_label = (
                        "Added"
                        if ingest_result.status == "new_document"
                        else ("Updated" if ingest_result.status == "updated_document" else "Verified")
                    )
                    details_list = []
                    if art_count:
                        details_list.append(f"{art_count} articles")
                    if rec_count:
                        details_list.append(f"{rec_count} recitals")
                    if para_count:
                        details_list.append(f"{para_count} paragraphs")

                    details_str = ", ".join(details_list) if details_list else "All provisions"

                    confirm_msg = (
                        f"✅ **Legislation Indexed: {short_name}**\n\n"
                        f"- **Title**: {doc_title}\n"
                        f"- **File**: `{filename}`\n"
                        f"- **Status**: {stat_label} in knowledge graph\n"
                        f"- **Content**: {details_str} with vector embeddings.\n\n"
                        f"You can now ask regulatory questions or cross-reference provisions from **{short_name}**."
                    )

                    # Append to conversation history so the agent has context
                    agent_system.conversation_history.append(
                        AIMessage(
                            content=(
                                f"Document '{short_name}' ({doc_title}) has been indexed with "
                                f"{details_str}. It is now available in the knowledge graph for questions."
                            )
                        )
                    )

                    await manager.send_message(
                        {"type": "message", "content": confirm_msg}, websocket
                    )

                except Exception as ingest_err:
                    logger.error(f"Ingestion failed: {ingest_err}", exc_info=True)
                    await manager.send_error(f"Failed to index document: {ingest_err}", websocket)

            else:
                user_text = payload.get("content", "")
                if not user_text.strip():
                    continue

                async def progress_cb(status_text: str) -> None:
                    await manager.send_message(
                        {"type": "status", "content": status_text},
                        websocket,
                    )

                response_chunks: list[str] = []
                async for chunk in agent_system.chat(user_text, on_status=progress_cb):
                    response_chunks.append(chunk)
                    await manager.send_message(
                        {"type": "stream", "content": chunk},
                        websocket,
                    )

                full_response = "".join(response_chunks).strip()
                if not full_response:
                    full_response = (
                        "Hello! I am here to help you explore and understand EU legislation. "
                        "How can I assist you today?"
                    )
                    await manager.send_message(
                        {"type": "stream", "content": full_response},
                        websocket,
                    )

                await manager.send_message(
                    {"type": "end", "content": full_response},
                    websocket,
                )

    except WebSocketDisconnect:
        await manager.disconnect(websocket)
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        await manager.send_error(str(e), websocket)
        await manager.disconnect(websocket)
