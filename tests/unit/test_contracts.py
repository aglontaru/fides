"""Unit tests for inter-agent communication contracts."""

from __future__ import annotations

import pytest

from fides.agents.contracts import (
    AgentType,
    Citation,
    IntentAnalysis,
    IntentEntities,
    LegalReview,
    LegalVerdict,
    TaskAssignment,
    TaskConstraints,
    TaskResult,
    TaskStatus,
    TodoItem,
    TodoList,
)


@pytest.mark.unit
def test_task_constraints_defaults():
    """Verify default task constraints are set correctly."""
    constraints = TaskConstraints()
    assert constraints.max_tool_calls == 8
    assert constraints.max_retries == 2
    assert constraints.timeout_seconds == 120


@pytest.mark.unit
def test_citation_serialization():
    """Verify citation model serializes and deserializes."""
    cit = Citation(
        document="EU AI Act",
        article="16",
        paragraph="1",
        text_excerpt="Providers of high-risk AI systems shall...",
    )
    data = cit.model_dump()
    assert data["document"] == "EU AI Act"
    assert data["article"] == "16"
    assert data["paragraph"] == "1"

    cit2 = Citation.model_validate(data)
    assert cit2 == cit


@pytest.mark.unit
def test_task_assignment_contract():
    """Verify TaskAssignment contract schema."""
    assignment = TaskAssignment(
        task_id="task-123",
        intent="Retrieve high-risk AI provider obligations",
        required_context={"domain": "AI", "topic": "obligations"},
        constraints=TaskConstraints(max_tool_calls=5),
        rag_scope="EU_AI_ACT",
    )
    assert assignment.task_id == "task-123"
    assert assignment.constraints.max_tool_calls == 5
    assert assignment.rag_scope == "EU_AI_ACT"


@pytest.mark.unit
def test_task_result_contract():
    """Verify TaskResult serializes and preserves status and citations."""
    result = TaskResult(
        task_id="task-123",
        status=TaskStatus.SUCCESS,
        findings="Found obligations under Article 16",
        citations=[
            Citation(document="EU AI Act", article="16", paragraph="1"),
        ],
        raw_context="Full text of Art. 16",
    )
    dumped = result.model_dump()
    assert dumped["status"] == "success"
    assert len(dumped["citations"]) == 1
    assert dumped["citations"][0]["article"] == "16"


@pytest.mark.unit
def test_legal_review_contract():
    """Verify LegalReview verdicts and validation."""
    review = LegalReview(
        task_id="rev-001",
        verdict=LegalVerdict.APPROVED,
        drafted_response="Providers must ensure compliance according to [EU AI Act, Art. 16].",
        completeness_score=0.98,
        feedback="High accuracy and proper citations.",
    )
    assert review.verdict == LegalVerdict.APPROVED
    assert review.completeness_score == 0.98
    assert not review.missing_citations


@pytest.mark.unit
def test_todo_list_dependencies():
    """Verify TodoList and TodoItem dependency tracking."""
    item1 = TodoItem(
        item_id="item-1",
        description="Query definition of AI system",
        target_agent=AgentType.QUERY,
    )
    item2 = TodoItem(
        item_id="item-2",
        description="Query obligations referencing definitions",
        target_agent=AgentType.QUERY,
        dependencies=["item-1"],
    )
    todo = TodoList(items=[item1, item2], replan_count=0)
    assert len(todo.items) == 2
    assert todo.items[1].dependencies == ["item-1"]
    assert todo.max_replans == 2


@pytest.mark.unit
def test_intent_analysis_schema():
    """Verify IntentAnalysis with entity extraction."""
    analysis = IntentAnalysis(
        intent_type="question",
        entities=IntentEntities(
            documents=["EU AI Act", "MDR"],
            articles=["16", "51"],
            terms=["high-risk AI", "custom-made device"],
        ),
        requires_legal_review=True,
        complexity="cross_document",
        raw_message="What are the provider obligations under AI Act Art 16 and MDR Art 51?",
    )
    assert analysis.requires_legal_review is True
    assert len(analysis.entities.documents) == 2
    assert len(analysis.entities.articles) == 2
