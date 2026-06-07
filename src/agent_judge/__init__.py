"""Agent-as-Judge: verify agent handoffs in multi-agent workflows."""

from agent_judge.audit import audit_handoff
from agent_judge.handoff_schemas import HandoffAuditRequest, HandoffAuditResponse
from agent_judge.judge import run_judge
from agent_judge.schemas import (
    CriterionEvaluation,
    JudgeInput,
    JudgeResult,
    RubricCriterion,
)

__all__ = [
    "run_judge",
    "audit_handoff",
    "JudgeInput",
    "JudgeResult",
    "HandoffAuditRequest",
    "HandoffAuditResponse",
    "RubricCriterion",
    "CriterionEvaluation",
]

__version__ = "0.2.0"
