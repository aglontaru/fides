import base64
import json
import logging
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from langchain_core.messages import AIMessage, HumanMessage

from fides.agents.factory import AgentSystem, create_agent_system
from fides.config.settings import get_settings
from fides.ingestion.pipeline import IngestionResult

logger = logging.getLogger(__name__)


def format_ingestion_confirmation(ingest_result: IngestionResult, filename: str) -> str:
    """Format an authoritative, structured confirmation for indexed legislation."""
    status = ingest_result.status
    if status == "new_document":
        status_desc = "The document is now marked as 'new_document' within Fides."
    elif status == "identical":
        status_desc = (
            "The document status remains 'identical' as no changes were made during indexing."
        )
    elif status == "updated_document":
        status_desc = "The document status has been updated to 'updated_document'."
    else:
        status_desc = f"The document status is '{status}'."

    short_name = ingest_result.short_name or "the regulation"

    # Generate relevant sample questions based on the indexed provisions
    sample_questions: list[str] = []
    if ingest_result.articles_count > 0:
        sample_questions.append(
            f"What is the main scope and core requirements established under {short_name}?"
        )
        sample_questions.append(
            f"What specific obligations, statutory exemptions, and liabilities apply under {short_name}?"
        )
    if ingest_result.recitals_count > 0:
        sample_questions.append(
            f"What legislative background, purposes, or principles are articulated in {short_name}?"
        )
    sample_questions.append(
        f"What are the key defined terms and their legal definitions in {short_name}?"
    )

    questions_block = "\n".join(f"{idx}. {q}" for idx, q in enumerate(sample_questions, 1))

    return (
        f"I have confirmed that the legal document '{filename}' has been successfully indexed into the Fides knowledge graph. "
        f"Here is a summary of what was done:\n\n"
        f'- **Document Title**: "{ingest_result.document_title}"\n'
        f"- **Identifier / Short Name**: {ingest_result.short_name}\n"
        f"- **Status**: {status_desc}\n"
        f"- **Indexed Provisions**:\n"
        f"  - Articles: {ingest_result.articles_count}\n"
        f"  - Paragraphs: {ingest_result.paragraphs_count}\n"
        f"  - Recitals: {ingest_result.recitals_count}\n\n"
        f"Here are some sample questions you can ask to explore this document:\n\n"
        f"{questions_block}\n\n"
        f"Feel free to ask specific questions or request citations from this document!"
    )


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
                    from neo4j import AsyncGraphDatabase

                    from fides.ingestion import IngestionPipeline

                    settings = get_settings()
                    driver = AsyncGraphDatabase.driver(
                        settings.neo4j_uri,
                        auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
                    )
                    try:
                        pipeline = IngestionPipeline(driver=driver, settings=settings)
                        ingest_result = await pipeline.ingest_pdf_bytes(
                            content_bytes=content_bytes,
                            filename=filename,
                            on_progress=progress_callback,
                        )
                    finally:
                        await driver.close()

                    if ingest_result.status == "error":
                        await manager.send_error(
                            f"Document processing failed: {ingest_result.message}", websocket
                        )
                        continue

                    # Build authoritative, structured confirmation message
                    confirmation_message = format_ingestion_confirmation(
                        ingest_result, filename
                    )

                    await manager.send_message(
                        {"type": "stream", "content": confirmation_message},
                        websocket,
                    )
                    await manager.send_message(
                        {"type": "end", "content": confirmation_message},
                        websocket,
                    )

                    # Update agent conversation history so subsequent user questions know
                    # about the newly indexed document and its provisions!
                    agent_system.conversation_history.append(
                        HumanMessage(
                            content=f"Uploaded document '{filename}' ({ingest_result.short_name})."
                        )
                    )
                    agent_system.conversation_history.append(
                        AIMessage(content=confirmation_message)
                    )

                except Exception as ingest_err:
                    logger.error(f"Document ingestion error: {ingest_err}", exc_info=True)
                    await manager.send_error(f"Failed to index document: {ingest_err}", websocket)

            else:
                user_text = payload.get("content", "")
                if not user_text.strip():
                    continue

                # Check for optional attachments directly in chat messages
                chat_attachments: list[bytes] = []
                attachment_filename: str | None = payload.get("filename")
                if "attachments" in payload and isinstance(payload["attachments"], list):
                    for att in payload["attachments"]:
                        try:
                            if isinstance(att, str):
                                chat_attachments.append(base64.b64decode(att))
                        except Exception as att_err:
                            logger.debug("Failed to decode attachment: %s", att_err)

                async def progress_cb(status_text: str) -> None:
                    await manager.send_message(
                        {"type": "status", "content": status_text},
                        websocket,
                    )

                chat_response_chunks: list[str] = []
                async for chunk in agent_system.chat(
                    user_text,
                    attachments=chat_attachments or None,
                    filename=attachment_filename,
                    on_status=progress_cb,
                ):
                    chat_response_chunks.append(chunk)
                    await manager.send_message(
                        {"type": "stream", "content": chunk},
                        websocket,
                    )

                full_response = "".join(chat_response_chunks).strip()
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
