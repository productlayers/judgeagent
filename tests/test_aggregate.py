"""Tests for deterministic verdict aggregation."""

from agent_judge.judge import aggregate_verdict
from agent_judge.schemas import (
    CriterionEvaluation,
    CriterionStatus,
    RubricCriterion,
    Verdict,
)


def test_critical_not_satisfied_fails():
    rubric = [
        RubricCriterion(id="a", requirement="req a", weight=1.0, critical=True),
        RubricCriterion(id="b", requirement="req b", weight=1.0, critical=False),
    ]
    evaluations = [
        CriterionEvaluation(
            id="a",
            requirement="req a",
            status=CriterionStatus.NOT_SATISFIED,
            confidence=0.9,
            reasoning="missing",
        ),
        CriterionEvaluation(
            id="b",
            requirement="req b",
            status=CriterionStatus.SATISFIED,
            confidence=0.9,
        ),
    ]
    result = aggregate_verdict(rubric, evaluations, [])
    assert result.verdict == Verdict.FAIL
    assert not result.can_continue


def test_high_satisfied_ratio_passes():
    rubric = [
        RubricCriterion(id="a", requirement="req a", weight=1.0),
        RubricCriterion(id="b", requirement="req b", weight=1.0),
    ]
    evaluations = [
        CriterionEvaluation(
            id="a",
            requirement="req a",
            status=CriterionStatus.SATISFIED,
            confidence=0.95,
        ),
        CriterionEvaluation(
            id="b",
            requirement="req b",
            status=CriterionStatus.SATISFIED,
            confidence=0.95,
        ),
    ]
    result = aggregate_verdict(rubric, evaluations, [])
    assert result.verdict == Verdict.PASS
    assert result.can_continue


def test_unsupported_only_is_uncertain():
    rubric = [RubricCriterion(id="a", requirement="req a", weight=1.0)]
    evaluations = [
        CriterionEvaluation(
            id="a",
            requirement="req a",
            status=CriterionStatus.UNSUPPORTED,
            confidence=0.5,
            reasoning="not proven",
        ),
    ]
    result = aggregate_verdict(rubric, evaluations, [])
    assert result.verdict == Verdict.UNCERTAIN
    assert not result.can_continue
