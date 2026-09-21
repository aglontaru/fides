"""
Inter-agent communication protocol for Fides.

This module defines Pydantic schemas for all communication between agents in the Fides system.
It serves as the foundational contract that every other agent module imports from.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class TaskStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class FailureReason(StrEnum):
    MISSING_PROVISION = "missing_provision"
    AMBIGUOUS_QUERY = "ambiguous_query"
    NO_RESULTS = "no_results"
    GRAPH_ERROR = "graph_error"
    TIMEOUT = "timeout"
    INSUFFICIENT_CONTEXT = "insufficient_context"


class LegalVerdict(StrEnum):
    APPROVED = "approved"
    NEEDS_REVISION = "needs_revision"
    REJECTED = "rejected"


class AgentType(StrEnum):
    QUERY = "query"
    INDEXING = "indexing"
    GRAPH_BUILDER = "graph_builder"
    DIFF = "diff"
    LEGAL = "legal"


class ItemStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class TaskConstraints(BaseModel):
    """Hard limits to prevent runaway agent loops."""

    max_tool_calls: int = 8
    max_retries: int = 2
    timeout_seconds: int = 120


class Citation(BaseModel):
    """A structured legal citation reference."""

    document: str
    article: str | None = None
    paragraph: str | None = None
    text_excerpt: str = ""


class TaskAssignment(BaseModel):
    """Orchestrator → Sub-agent delegation contract."""

    task_id: str
    intent: str
    required_context: dict[str, Any] = {}
    constraints: TaskConstraints = TaskConstraints()
    rag_scope: str | None = None


class TaskResult(BaseModel):
    """Sub-agent → Orchestrator response contract."""

    task_id: str
    status: TaskStatus
    findings: str
    citations: list[Citation] = []
    failure_reason: FailureReason | None = None
    recommended_action: str | None = None
    raw_context: str = ""
    metadata: dict[str, Any] = {}


class LegalReview(BaseModel):
    """Legal Agent → Orchestrator review verdict."""

    task_id: str
    verdict: LegalVerdict
    drafted_response: str
    missing_citations: list[str] = []
    factual_issues: list[str] = []
    completeness_score: float = 1.0
    feedback: str = ""


class TodoItem(BaseModel):
    """Single item in the Orchestrator's execution plan."""

    item_id: str
    description: str
    target_agent: AgentType
    status: ItemStatus = ItemStatus.PENDING
    dependencies: list[str] = []
    result: TaskResult | None = None
    attempts: int = 0
    max_attempts: int = 2


class TodoList(BaseModel):
    """The Orchestrator's complete execution plan for a user turn."""

    items: list[TodoItem]
    replan_count: int = 0
    max_replans: int = 2


class IntentEntities(BaseModel):
    """Entities extracted from the user's message."""

    documents: list[str] = []
    articles: list[str] = []
    terms: list[str] = []


class IntentAnalysis(BaseModel):
    """Result of the Orchestrator's intent extraction."""

    intent_type: str
    entities: IntentEntities
    requires_legal_review: bool
    complexity: str
    raw_message: str


__all__ = [
    "AgentType",
    "Citation",
    "FailureReason",
    "IntentAnalysis",
    "IntentEntities",
    "ItemStatus",
    "LegalReview",
    "LegalVerdict",
    "TaskAssignment",
    "TaskConstraints",
    "TaskResult",
    "TaskStatus",
    "TodoItem",
    "TodoList",
]
