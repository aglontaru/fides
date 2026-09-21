"""Fides autonomous agents package."""

from __future__ import annotations

from fides.agents.contracts import (
    AgentType,
    Citation,
    FailureReason,
    IntentAnalysis,
    IntentEntities,
    ItemStatus,
    LegalReview,
    LegalVerdict,
    TaskAssignment,
    TaskConstraints,
    TaskResult,
    TaskStatus,
    TodoItem,
    TodoList,
)
from fides.agents.factory import AgentSystem, create_agent_system
from fides.agents.orchestrator import create_orchestrator, is_simple_greeting, route_intent
from fides.agents.sub_agents import (
    create_diff_subagent,
    create_indexing_subagent,
    create_legal_subagent,
    create_query_subagent,
)

__all__ = [
    "AgentSystem",
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
    "create_agent_system",
    "create_diff_subagent",
    "create_indexing_subagent",
    "create_legal_subagent",
    "create_orchestrator",
    "create_query_subagent",
    "is_simple_greeting",
    "route_intent",
]
