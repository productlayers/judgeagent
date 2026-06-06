"""Agent-as-Judge: verify agent handoffs in multi-agent workflows."""

from agent_judge.judge import run_judge
from agent_judge.schemas import (
    CriterionEvaluation,
    JudgeInput,
    JudgeResult,
    RubricCriterion,
)

__all__ = [
    "run_judge",
    "JudgeInput",
    "JudgeResult",
    "RubricCriterion",
    "CriterionEvaluation",
]

__version__ = "0.1.0"
