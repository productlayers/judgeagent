"""Tests for handoff audit schemas and service."""

from agent_judge.audit import audit_handoff, get_handoff_stats, reset_handoff_stats
from agent_judge.handoff_schemas import (
    EvidenceBundle,
    HandoffAuditRequest,
    LangGraphHandoffContext,
)
from agent_judge.schemas import JudgeResult, Verdict
from unittest.mock import patch


def _request() -> HandoffAuditRequest:
    return HandoffAuditRequest(
        langgraph=LangGraphHandoffContext(
            graph_id="test_graph",
            thread_id="thread-1",
            from_node="planner",
            to_node="booker",
            attempt=1,
        ),
        original_goal="Do the thing completely.",
        agent_claim="Done.",
        evidence=EvidenceBundle(output="partial output only"),
    )


def test_evidence_bundle_flattens():
    bundle = EvidenceBundle(
        output="hello",
        tool_calls=[],
        artifacts=["file://a.csv"],
    )
    text = bundle.to_evidence_text()
    assert "hello" in text
    assert "file://a.csv" in text


def test_handoff_audit_response_routing_on_pass():
    reset_handoff_stats()
    judge_result = JudgeResult(
        verdict=Verdict.PASS,
        can_continue=True,
        confidence=0.9,
        summary="ok",
        rubric=[],
        evaluations=[],
    )
    with patch("agent_judge.audit.run_judge", return_value=judge_result):
        response = audit_handoff(_request())
    assert response.next_node == "booker"
    assert not response.should_interrupt
    assert response.redis is not None
    assert "workflow:thread-1" in response.redis.workflow_key


def test_handoff_audit_response_routing_on_uncertain():
    judge_result = JudgeResult(
        verdict=Verdict.UNCERTAIN,
        can_continue=False,
        confidence=0.4,
        summary="need more",
        rubric=[],
        evaluations=[],
    )
    with patch("agent_judge.audit.run_judge", return_value=judge_result):
        response = audit_handoff(_request())
    assert response.should_interrupt
    assert response.next_node is None


def test_handoff_stats_increment():
    reset_handoff_stats()
    fail_result = JudgeResult(
        verdict=Verdict.FAIL,
        can_continue=False,
        confidence=0.8,
        summary="fail",
        rubric=[],
        evaluations=[],
    )
    pass_result = fail_result.model_copy(
        update={"verdict": Verdict.PASS, "can_continue": True, "summary": "pass"}
    )
    req = _request()
    with patch("agent_judge.audit.run_judge", return_value=fail_result):
        audit_handoff(req)
    with patch("agent_judge.audit.run_judge", return_value=pass_result):
        audit_handoff(req)
    stats = get_handoff_stats("test_graph", "planner→booker")
    assert stats.total == 2
    assert stats.fail_count == 1
    assert stats.pass_count == 1
    assert stats.pass_rate == 0.5
