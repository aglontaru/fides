"""Factory and lifecycle management for the Fides autonomous multi-agent system."""

from __future__ import annotations

import inspect
from collections.abc import AsyncIterator, Callable, Sequence
from typing import Any

import structlog
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict

from fides.agents.orchestrator import create_orchestrator, is_simple_greeting
from fides.agents.prompts import LEGAL_AGENT_SYSTEM_PROMPT
from fides.config import create_chat_model
from fides.config.llm import create_agent_model
from fides.config.settings import FidesSettings, get_settings

logger: structlog.stdlib.BoundLogger = structlog.stdlib.get_logger(__name__)


async def _notify_status(callback: Callable[[str], Any] | None, message: str) -> None:
    """Safely invoke status callback whether it is sync or async."""
    if callback is None:
        return
    try:
        res = callback(message)
        if inspect.isawaitable(res):
            await res
    except Exception as e:
        logger.debug("Status callback failed", error=str(e))


def _trim_history_by_tokens(
    messages: list[BaseMessage], max_tokens: int = 16000
) -> list[BaseMessage]:
    """Retain conversation history up to the configured token budget."""
    total_tokens = 0
    trimmed: list[BaseMessage] = []
    for msg in reversed(messages):
        text = str(msg.content)
        # Standard heuristic: ~4 characters per token + overhead
        tokens = len(text) // 4 + 10
        if total_tokens + tokens > max_tokens:
            break
        total_tokens += tokens
        trimmed.append(msg)
    return list(reversed(trimmed))


def clean_agent_monologue(text: str) -> str:
    """Normalize internal agent mentions, meta-dialogue, and scaffold headers from user-facing text."""
    phrases = [
        "Based on the summary provided by the Query Agent regarding",
        "Based on the summary provided by the Query Agent,",
        "Based on the summary provided by the Query Agent",
        "Based on the information provided by the Query Agent regarding",
        "Based on the information provided by the Query Agent,",
        "Based on the information provided by the Query Agent",
        "According to the Query Agent,",
        "According to the Query Agent",
        "The Query Agent found that",
        "The Query Agent retrieved",
    ]
    cleaned = text
    for p in phrases:
        cleaned = cleaned.replace(p, "Based on the retrieved legal provisions,")

    # Strip meta-prompt scaffold headers if leaked by smaller models
    scaffold_replacements = [
        ("### Phase 1: Evidence Critique & Exemption Audit", "### Operative Legal Analysis"),
        ("### Phase 1: Evidence Critique & Exemption Audit\n", ""),
        ("### Phase 2: NotebookLM Strict Grounding & Citation Drafting", "### Operative Legal Analysis"),
        ("### Phase 2: Notebooks & Strict Grounding & Citation Drafting", "### Operative Legal Analysis"),
        ("### Phase 2: NotebookLM Strict Grounding", ""),
        ("Phase 1: Evidence Critique & Exemption Audit", "### Operative Legal Analysis"),
        ("Phase 2: NotebookLM Strict Grounding & Citation Drafting", "### Operative Legal Analysis"),
        ("**NotebookLM Strict Grounding & Citation Drafting**", ""),
    ]
    for old, new in scaffold_replacements:
        cleaned = cleaned.replace(old, new)

    return cleaned


def _extract_records_from_tool_output(
    tool_name: str, tool_output: object
) -> list[dict[str, Any]]:
    """Extract structured provision records from raw tool outputs."""
    if not tool_output:
        return []
    records: list[dict[str, Any]] = []
    try:
        raw_data = tool_output
        if isinstance(raw_data, str):
            import json

            try:
                raw_data = json.loads(raw_data)
            except Exception:
                return []
        if isinstance(raw_data, dict):
            if "data" in raw_data and isinstance(raw_data["data"], list):
                raw_data = raw_data["data"]
            elif "status" in raw_data and "data" in raw_data:
                raw_data = raw_data["data"]
            else:
                raw_data = [raw_data]
        if isinstance(raw_data, list):
            for item in raw_data:
                if isinstance(item, dict):
                    records.append(item)
    except Exception as e:
        logger.debug("Failed extracting records from tool output", tool=tool_name, error=str(e))
    return records


def _format_evidence_bundle(records: list[dict[str, Any]], max_chars: int = 7500) -> str:
    """Format structured provision records into a unified statutory evidence package with strict budgeting."""
    if not records:
        return "No statutory provisions retrieved from the knowledge graph."

    # Sort records by score descending if available
    sorted_records = sorted(
        records,
        key=lambda r: float(r.get("score") or 0.0),
        reverse=True,
    )

    lines: list[str] = []
    current_chars = 0

    for rec in sorted_records:
        doc = rec.get("document") or "Document"
        pid = rec.get("provision_id") or rec.get("id") or rec.get("article_id") or "Provision"
        title = rec.get("article_title") or rec.get("title") or ""
        text = (
            rec.get("paragraph_text")
            or rec.get("full_text")
            or rec.get("text")
            or ""
        ).strip()

        # Cap any individual monolithic section/annex at 1,500 characters
        # so a single massive annex cannot starve out other operative articles
        if len(text) > 1500:
            text = text[:1500] + "\n[... provision text truncated to retain key operative rules ...]"

        cites = rec.get("cited_articles") or []
        annexes = rec.get("referenced_annexes") or []

        header = f"=== PROVISION: {pid}"
        if doc:
            header += f" | {doc}"
        if title:
            header += f" | {title}"
        header += " ==="

        entry_lines = [header]
        if text:
            entry_lines.append(text)
        if cites:
            entry_lines.append(f"Cross-References Cited: {', '.join(cites)}")
        if annexes:
            entry_lines.append(f"Annexes Referenced: {', '.join(annexes)}")
        entry_lines.append("")

        entry_text = "\n".join(entry_lines)
        if current_chars + len(entry_text) > max_chars and lines:
            # Exceeded budget, stop appending further lower-scoring items
            break

        lines.append(entry_text)
        current_chars += len(entry_text)

    return "\n".join(lines)


class AgentSystem(BaseModel):
    """Manages conversational chat, autonomous multi-agent delegation, and history."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    agent: Any
    mcp_client: Any
    llm: Any = None
    settings: Any = None
    conversation_history: list[BaseMessage] = []

    async def chat(
        self,
        message: str,
        attachments: list[bytes] | None = None,
        filename: str | None = None,
        on_status: Callable[[str], Any] | None = None,
    ) -> AsyncIterator[str]:
        """Stream response for a chat message using the autonomous DeepAgent Orchestrator.

        Dispatches through self.agent (the DeepAgent CompiledStateGraph), coordinating
        the Query, Indexing, Diff, Graph Builder, and Legal agents, with full LangSmith tracing.

        Args:
            message: The user's input message.
            attachments: Optional list of document attachments (bytes).
            filename: Optional filename for attached documents.
            on_status: Optional callback for progress and status messages.

        Yields:
            Chunks of the orchestrator's response string as they are generated.
        """
        logger.info("Processing chat message via Autonomous DeepAgent", message_length=len(message))
        clean_text = message.strip()
        if not clean_text and not attachments:
            return

        # Handle document attachment context if present
        if attachments:
            file_label = filename or "document.pdf"
            attachment_context = (
                f"[Attached Document: '{file_label}' ({len(attachments[0])} bytes)]\n\n"
            )
            clean_text = f"{attachment_context}{clean_text}"

        await _notify_status(on_status, "Orchestrator analyzing request and formulating plan...")

        # Build message history trimmed to token budget
        max_tokens = getattr(self.settings, "max_conversation_tokens", 16000)
        history = _trim_history_by_tokens(self.conversation_history, max_tokens=max_tokens)
        messages = [
            *history,
            HumanMessage(content=clean_text),
        ]
        inputs = {"messages": messages}

        response_parts: list[str] = []
        turn_buffers: dict[str, list[str]] = {}
        query_called = False
        legal_called = False
        latest_legal_output: str = ""
        raw_retrieved_records: list[dict[str, Any]] = []
        retrieved_provision_ids: set[str] = set()

        if self.agent is not None:
            try:
                async for ev in self.agent.astream_events(inputs, version="v2"):
                    kind = ev["event"]
                    name = ev.get("name", "")
                    run_id = ev.get("run_id", "")
                    metadata = ev.get("metadata", {})
                    agent_name = metadata.get("lc_agent_name", "")
                    is_subagent = metadata.get("ls_agent_type") == "subagent" or agent_name in (
                        "query",
                        "indexing",
                        "graph_builder",
                        "diff",
                        "legal",
                    )

                    if kind == "on_chat_model_start":
                        if not is_subagent and run_id:
                            turn_buffers[run_id] = []

                    elif kind == "on_chat_model_stream":
                        if not is_subagent and run_id:
                            chunk = ev["data"]["chunk"]
                            content = getattr(chunk, "content", "")
                            if content and isinstance(content, str):
                                turn_buffers.setdefault(run_id, []).append(content)

                    elif kind == "on_chat_model_end":
                        if not is_subagent and run_id in turn_buffers:
                            output = ev["data"].get("output")
                            tool_calls = getattr(output, "tool_calls", None) or []
                            if tool_calls:
                                # Model decided to call tools: discard preliminary text to prevent monologue leakage
                                turn_buffers.pop(run_id, None)
                            else:
                                # Final synthesis turn without tool calls
                                final_text = "".join(turn_buffers.pop(run_id, [])).strip()
                                if not final_text and hasattr(output, "content"):
                                    out_content = output.content
                                    if isinstance(out_content, str):
                                        final_text = out_content.strip()
                                    elif isinstance(out_content, list):
                                        final_text = "".join(
                                            b.get("text", "") if isinstance(b, dict) else str(b)
                                            for b in out_content
                                        ).strip()

                                if final_text:
                                    cleaned_text = clean_agent_monologue(final_text)
                                    response_parts.append(cleaned_text)
                                    yield cleaned_text

                    elif kind == "on_tool_start":
                        tool_input = ev["data"].get("input", {})
                        if name == "task" and isinstance(tool_input, dict):
                            sub_type = tool_input.get("subagent_type", "subagent")
                            if sub_type == "query":
                                await _notify_status(
                                    on_status,
                                    "Searching legislation knowledge graph and identifying operative provisions...",
                                )
                            elif sub_type == "indexing":
                                await _notify_status(
                                    on_status,
                                    "Indexing legislation into knowledge graph...",
                                )
                            elif sub_type == "graph_builder":
                                await _notify_status(
                                    on_status,
                                    "Discovering dynamic ontology, new node types, and building graph relationships...",
                                )
                            elif sub_type == "diff":
                                await _notify_status(
                                    on_status,
                                    "Comparing legislative provisions and analyzing changes...",
                                )
                            elif sub_type == "legal":
                                await _notify_status(
                                    on_status,
                                    "Verifying operative provisions, statutory exemptions, and drafting legal analysis...",
                                )
                            else:
                                await _notify_status(
                                    on_status,
                                    "Analyzing regulatory requirements...",
                                )
                        elif isinstance(tool_input, dict) and "query_text" in tool_input:
                            await _notify_status(
                                on_status,
                                "Retrieving regulatory provisions from knowledge graph...",
                            )
                        else:
                            await _notify_status(
                                on_status,
                                "Processing legal provisions...",
                            )

                    elif kind == "on_tool_end":
                        tool_output = ev["data"].get("output")
                        if name == "task":
                            tool_input = ev["data"].get("input", {})
                            sub_type = (
                                tool_input.get("subagent_type", "subagent")
                                if isinstance(tool_input, dict)
                                else "subagent"
                            )
                            if sub_type == "query":
                                query_called = True
                                await _notify_status(
                                    on_status,
                                    "Provisions retrieved. Analyzing statutory scope and exceptions...",
                                )
                            elif sub_type == "legal":
                                legal_called = True
                                if tool_output:
                                    if hasattr(tool_output, "content"):
                                        latest_legal_output = str(tool_output.content)
                                    else:
                                        latest_legal_output = str(tool_output)
                                await _notify_status(
                                    on_status,
                                    "Legal analysis and citations verified.",
                                )
                            else:
                                await _notify_status(
                                    on_status,
                                    "Task completed.",
                                )
                        elif name in (
                            "hybrid_search",
                            "get_provision",
                            "get_article",
                            "get_article_with_context",
                            "neo4j_query",
                            "vector_search",
                        ):
                            query_called = True
                            extracted = _extract_records_from_tool_output(name, tool_output)
                            for r in extracted:
                                pid = r.get("provision_id") or r.get("id") or r.get("article_id")
                                if pid and pid not in retrieved_provision_ids:
                                    retrieved_provision_ids.add(pid)
                                    raw_retrieved_records.append(r)

            except Exception as stream_err:
                logger.error(
                    "Error streaming autonomous agent response", error=str(stream_err), exc_info=True
                )
        elif self.llm is not None:
            try:
                res = await self.llm.ainvoke(messages)
                content = getattr(res, "content", "")
                if isinstance(content, str) and content:
                    response_parts.append(content)
                    yield content
            except Exception as llm_err:
                logger.error("Direct LLM execution error", error=str(llm_err))

        # Multi-Turn Deliberation Gate:
        # Guarantees that every substantive legal inquiry is grounded in retrieved text,
        # audits statutory exemptions and negative qualifiers, and enforces NotebookLM citations.
        from fides.config.agent_config import load_agent_config

        agent_cfg = load_agent_config()
        is_substantive = not is_simple_greeting(clean_text)
        has_citations = any("[" in p and "]" in p for p in response_parts)

        if (
            agent_cfg.global_settings.enable_deliberation_gate
            and is_substantive
            and not response_parts
        ):
            # 1. If retrieval was skipped or agent failed to synthesize, execute deep retrieval now
            if not raw_retrieved_records:
                await _notify_status(
                    on_status,
                    "Orchestrator deliberating: retrieving authoritative provisions from knowledge graph...",
                )
                try:
                    from fides.mcp_server.tools.vector_tools import hybrid_search

                    direct_search_res = await hybrid_search(clean_text, top_k=15)
                    direct_records = _extract_records_from_tool_output(
                        "hybrid_search", direct_search_res
                    )
                    for r in direct_records:
                        pid = r.get("provision_id") or r.get("id") or r.get("article_id")
                        if pid and pid not in retrieved_provision_ids:
                            retrieved_provision_ids.add(pid)
                            raw_retrieved_records.append(r)
                except Exception as r_err:
                    logger.warning("Deliberative retrieval fallback failed", error=str(r_err))

            # 2. Multi-turn cross-reference resolution (ReAct graph expansion)
            # Expand cross-references only from the TOP 2 retrieved provisions
            missing_annexes: set[str] = set()
            missing_articles: set[str] = set()
            for r in raw_retrieved_records[:2]:
                for an in r.get("referenced_annexes") or []:
                    if an and an not in retrieved_provision_ids and len(missing_annexes) < 1:
                        missing_annexes.add(an)
                for ca in r.get("cited_articles") or []:
                    if ca and ca not in retrieved_provision_ids and len(missing_articles) < 2:
                        missing_articles.add(ca)

            if missing_annexes or missing_articles:
                try:
                    from fides.mcp_server.tools.neo4j_tools import get_provision

                    for ref_id in list(missing_annexes) + list(missing_articles):
                        await _notify_status(
                            on_status,
                            f"Expanding statutory context: retrieving cross-referenced provision {ref_id}...",
                        )
                        ref_res = await get_provision(ref_id)
                        ref_recs = _extract_records_from_tool_output("get_provision", ref_res)
                        for rr in ref_recs:
                            rpid = rr.get("provision_id") or rr.get("id") or ref_id
                            if rpid not in retrieved_provision_ids:
                                retrieved_provision_ids.add(rpid)
                                raw_retrieved_records.append(rr)
                except Exception as xref_err:
                    logger.debug("Cross-reference expansion error", error=str(xref_err))

            # 3. Deliberative legal critique and NotebookLM citation drafting
            await _notify_status(
                on_status,
                "Auditing statutory evidence, negative qualifiers, and drafting cited brief via Legal Agent...",
            )
            try:
                legal_llm = create_agent_model("legal", self.settings)
                evidence_text = _format_evidence_bundle(raw_retrieved_records)
                legal_prompt = (
                    f"User Legal Inquiry:\n{clean_text}\n\n"
                    f"Statutory Evidence Package from Knowledge Graph:\n{evidence_text}\n\n"
                    "Prepare an authoritative, citation-backed legal memorandum addressing all aspects of the user's inquiry.\n"
                    "Requirements:\n"
                    "- If the inquiry contains specific numbered questions or points (e.g. 1, 2, 3), systematically address each point directly under the Operative Legal Analysis.\n"
                    "- Focus strictly on the exact device classification or entity requested (e.g., custom-made Class III devices). Do not drift into generic Class I or standard device rules.\n"
                    "- Provide exact inline citations in [Document, Provision/Section/Art. X, Para. Y] format for every substantive legal conclusion.\n"
                    "- Strictly examine statutory exemptions, negative qualifiers (e.g. 'other than custom-made', 'shall not apply'), and specialized regimes.\n"
                    "- Structure your response with standard Markdown headings:\n"
                    "  ### Executive Summary\n"
                    "  ### Operative Legal Analysis\n"
                    "  ### Statutory Exemptions & Special Regimes\n"
                    "  ### Procedural & Documentary Requirements\n"
                    "- Do NOT output any internal phase labels (e.g., do NOT write 'Phase 1' or 'Phase 2').\n"
                    "- If any aspect is not addressed in the retrieved text, state factually that based on the indexed documents it is not addressed."
                )
                legal_res = await legal_llm.ainvoke(
                    [
                        SystemMessage(content=LEGAL_AGENT_SYSTEM_PROMPT),
                        HumanMessage(content=legal_prompt),
                    ]
                )
                legal_text = getattr(legal_res, "content", "")
                if isinstance(legal_text, str) and legal_text.strip():
                    verified_text = clean_agent_monologue(legal_text.strip())
                    response_parts = [verified_text]
                    yield verified_text
            except Exception as leg_err:
                logger.warning("Deliberation gate synthesis failed", error=str(leg_err))

        full_res = "".join(response_parts).strip()
        if not full_res and latest_legal_output:
            cleaned = clean_agent_monologue(latest_legal_output.strip())
            response_parts = [cleaned]
            yield cleaned
            full_res = cleaned

        if not full_res:
            full_res = (
                "I processed your query against the legislation knowledge graph, but could not formulate "
                "a conclusive answer. Please refine your question or specify the regulation of interest."
            )
            yield full_res

        self.conversation_history.append(HumanMessage(content=clean_text))
        self.conversation_history.append(AIMessage(content=full_res))

    async def close(self) -> None:
        """Close the MCP client connection and perform cleanup."""
        logger.info("Closing AgentSystem")
        if hasattr(self.mcp_client, "close") and callable(self.mcp_client.close):
            try:
                await self.mcp_client.close()
            except Exception as e:
                logger.debug("Error closing MCP client", error=str(e))


async def create_agent_system(
    settings: FidesSettings | None = None,
    mcp_tools: Sequence[BaseTool] | None = None,
) -> AgentSystem:
    """Create the complete autonomous Fides agent system.

    Returns an AgentSystem managing the DeepAgent orchestrator and MCP connections.
    """
    logger.info("Creating autonomous agent system")
    s = settings or get_settings()

    agent, mcp_client = await create_orchestrator(settings=s, mcp_tools=mcp_tools)
    llm = create_chat_model(s)

    return AgentSystem(
        agent=agent,
        mcp_client=mcp_client,
        llm=llm,
        settings=s,
        conversation_history=[],
    )


__all__ = [
    "AgentSystem",
    "create_agent_system",
]
