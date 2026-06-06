"""Pydantic schemas for the judge's structured inputs and outputs.

These models are the contract between calling agents/orchestrators and the
judge. Outputs are intentionally strict and machine-readable so that an
orchestration system can branch on `verdict` / `can_continue` automatically.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class Verdict(str, Enum):
    """Overall judgement of whether a handoff is allowed to proceed."""

    PASS = "pass"
    FAIL = "fail"
    UNCERTAIN = "uncertain"


class CriterionStatus(str, Enum):
    """Per-criterion outcome.

    - satisfied: the evidence proves this criterion is met.
    - not_satisfied: the evidence shows this criterion is NOT met.
    - unsupported: the claim asserts this but the evidence does not prove it.
    """

    SATISFIED = "satisfied"
    NOT_SATISFIED = "not_satisfied"
    UNSUPPORTED = "unsupported"


# --------------------------------------------------------------------------- #
# Input
# --------------------------------------------------------------------------- #


class JudgeInput(BaseModel):
    """Everything the judge needs to verify a single handoff."""

    original_goal: str = Field(
        ...,
        description=(
            "The original task/goal given to the agent (the source of truth "
            "the rubric is derived from)."
        ),
    )
    agent_system_prompt: str = Field(
        default="",
        description=(
            "The system prompt / role the agent was operating under. Used to "
            "refine the rubric and to suggest prompt improvements."
        ),
    )
    agent_claim: str = Field(
        ...,
        description="The agent's completion claim (e.g. 'Done, I created ...').",
    )
    evidence: str = Field(
        default="",
        description=(
            "The actual artifacts/output produced by the agent. This is what "
            "the claim is checked against (the itinerary, files, logs, etc.)."
        ),
    )
    workflow_context: str = Field(
        default="",
        description=(
            "Optional context about the surrounding workflow: what the next "
            "step needs, prior steps, constraints, etc."
        ),
    )


# --------------------------------------------------------------------------- #
# Intermediate artifacts
# --------------------------------------------------------------------------- #


class RubricCriterion(BaseModel):
    """A single, checkable requirement derived from the goal."""

    id: str = Field(..., description="Short stable identifier, e.g. 'flights'.")
    requirement: str = Field(
        ..., description="A concrete, verifiable requirement to check."
    )
    weight: float = Field(
        default=1.0,
        ge=0.0,
        description="Relative importance of this criterion (>= 0).",
    )
    critical: bool = Field(
        default=False,
        description=(
            "If true, failing this criterion alone should fail the handoff "
            "regardless of weighted score."
        ),
    )


class CriterionEvaluation(BaseModel):
    """The judge's assessment of one rubric criterion against the evidence."""

    id: str = Field(..., description="Matches RubricCriterion.id.")
    requirement: str = Field(..., description="The requirement being evaluated.")
    status: CriterionStatus = Field(
        ..., description="satisfied / not_satisfied / unsupported."
    )
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Confidence in this individual judgement (0-1).",
    )
    reasoning: str = Field(
        default="",
        description="Why this status was chosen, grounded in the evidence.",
    )
    evidence_quote: str = Field(
        default="",
        description="The snippet of evidence that supports the judgement, if any.",
    )


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #


class JudgeResult(BaseModel):
    """The full, structured verdict returned by `judge_handoff`."""

    verdict: Verdict = Field(
        ..., description="pass / fail / uncertain."
    )
    can_continue: bool = Field(
        ...,
        description=(
            "Convenience flag for orchestrators. True only when verdict==pass."
        ),
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Overall confidence in the verdict (0-1)."
    )
    summary: str = Field(
        ..., description="A short human-readable summary of the decision."
    )
    rubric: List[RubricCriterion] = Field(
        default_factory=list,
        description="The rubric derived from the original goal.",
    )
    evaluations: List[CriterionEvaluation] = Field(
        default_factory=list,
        description="Per-criterion evaluation results.",
    )
    missing_evidence: List[str] = Field(
        default_factory=list,
        description="Requirements that the evidence did not prove.",
    )
    failure_reasons: List[str] = Field(
        default_factory=list,
        description="Concrete reasons the handoff failed (empty when passing).",
    )
    suggested_next_action: str = Field(
        default="",
        description=(
            "What the orchestrator/agent should do next "
            "(proceed, fix X, gather more evidence, etc.)."
        ),
    )
    prompt_improvements: List[str] = Field(
        default_factory=list,
        description=(
            "Suggestions to improve the agent's prompt so the failure is less "
            "likely next time."
        ),
    )
    consensus_runs: int = Field(
        default=1,
        ge=1,
        description="How many independent judge runs were aggregated.",
    )

    @classmethod
    def uncertain_fallback(cls, reason: str) -> "JudgeResult":
        """Build a safe 'uncertain' result for error paths.

        Failing closed (uncertain, can_continue=False) is the conservative
        choice when the judge itself errors out.
        """
        return cls(
            verdict=Verdict.UNCERTAIN,
            can_continue=False,
            confidence=0.0,
            summary=f"Judge could not complete a reliable evaluation: {reason}",
            rubric=[],
            evaluations=[],
            missing_evidence=[],
            failure_reasons=[reason],
            suggested_next_action=(
                "Resolve the judge error and/or supply more evidence, then "
                "re-run the handoff check."
            ),
            prompt_improvements=[],
            consensus_runs=1,
        )
