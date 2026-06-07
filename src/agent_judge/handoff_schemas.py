"""Orchestration-layer schemas for LangGraph handoff audits.

These extend the core JudgeInput / JudgeResult contract with LangGraph identity,
structured evidence bundles, and optional Weave trace references.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from agent_judge.schemas import JudgeInput, JudgeResult, Verdict


class EvidenceSource(str, Enum):
    """How historical run data was supplied."""

    INLINE = "inline"
    WEAVE = "weave"
    LANGGRAPH_STATE = "langgraph_state"


class ToolCallRecord(BaseModel):
    """One tool invocation captured from the audited agent's run."""

    name: str
    args: Dict[str, Any] = Field(default_factory=dict)
    result: str = ""
    error: Optional[str] = None


class EvidenceBundle(BaseModel):
    """Structured artifacts from the historical run being audited."""

    output: str = Field(default="", description="Primary agent output.")
    tool_calls: List[ToolCallRecord] = Field(default_factory=list)
    artifacts: List[str] = Field(
        default_factory=list,
        description="URIs or paths to supporting files.",
    )

    def to_evidence_text(self) -> str:
        """Flatten to the string format expected by the core judge."""
        parts: List[str] = []
        if self.output:
            parts.append(f"OUTPUT:\n{self.output}")
        if self.tool_calls:
            parts.append("TOOL CALLS:")
            for tc in self.tool_calls:
                detail = tc.result or tc.error or ""
                parts.append(f"  - {tc.name}({tc.args}) -> {detail}")
        if self.artifacts:
            parts.append("ARTIFACTS:\n" + "\n".join(f"  - {a}" for a in self.artifacts))
        return "\n\n".join(parts)


class WeaveRef(BaseModel):
    """Optional pointer to a W&B Weave trace for this agent run."""

    project: str
    trace_id: str = Field(..., description="Weave call/trace ID for the agent run.")
    op_name: Optional[str] = Field(
        default=None,
        description="Specific op within the trace, e.g. planner_node.",
    )


class LangGraphHandoffContext(BaseModel):
    """Identifies a handoff within a LangGraph execution."""

    graph_id: str = Field(..., description="Stable graph name, e.g. travel_pipeline_v1.")
    thread_id: str = Field(..., description="LangGraph configurable.thread_id.")
    checkpoint_id: Optional[str] = Field(
        default=None,
        description="LangGraph checkpoint at the handoff.",
    )
    run_id: Optional[str] = Field(
        default=None,
        description="LangGraph run_id when available.",
    )
    from_node: str = Field(..., description="Completing node, e.g. planner.")
    to_node: str = Field(..., description="Target node if pass, e.g. booker.")
    from_agent: Optional[str] = Field(default=None)
    to_agent: Optional[str] = Field(default=None)
    attempt: int = Field(default=1, ge=1)

    @property
    def handoff_key(self) -> str:
        return f"{self.from_node}→{self.to_node}"


class HandoffAuditRequest(BaseModel):
    """Full audit request for a LangGraph handoff edge."""

    langgraph: LangGraphHandoffContext
    original_goal: str
    agent_claim: str
    agent_system_prompt: str = ""
    workflow_context: str = ""
    evidence_source: EvidenceSource = EvidenceSource.INLINE
    evidence: EvidenceBundle = Field(default_factory=EvidenceBundle)
    weave: Optional[WeaveRef] = None
    state_snapshot: Dict[str, Any] = Field(default_factory=dict)

    def to_judge_input(self) -> JudgeInput:
        """Adapt to the core judge contract."""
        return JudgeInput(
            original_goal=self.original_goal,
            agent_system_prompt=self.agent_system_prompt,
            agent_claim=self.agent_claim,
            evidence=self.evidence.to_evidence_text(),
            workflow_context=self.workflow_context,
        )


class StructuredRecommendation(BaseModel):
    """Actionable fix surfaced to orchestrators and UI layers."""

    type: Literal[
        "prompt_patch", "gather_evidence", "retry_node", "escalate_human"
    ]
    title: str
    description: str
    prompt_before: Optional[str] = None
    prompt_after: Optional[str] = None
    target_node: Optional[str] = None
    related_criterion_ids: List[str] = Field(default_factory=list)


class HandoffStats(BaseModel):
    """Rolling pass/fail counters for a handoff edge."""

    total: int = 0
    pass_count: int = 0
    fail_count: int = 0
    uncertain_count: int = 0

    @property
    def pass_rate(self) -> float:
        return self.pass_count / self.total if self.total else 0.0


class RedisRef(BaseModel):
    """Key naming convention for live orchestration (Redis integration)."""

    workflow_key: str
    stats_key: str
    event_channel: str


class HandoffAuditResponse(BaseModel):
    """Judge result plus LangGraph routing hints and integration metadata."""

    audit_id: str
    result: JudgeResult
    langgraph: LangGraphHandoffContext
    next_node: Optional[str] = None
    should_interrupt: bool = False
    recommendations: List[StructuredRecommendation] = Field(default_factory=list)
    handoff_stats: Optional[HandoffStats] = None
    weave_trace_id: Optional[str] = None
    redis: Optional[RedisRef] = None

    @classmethod
    def from_judge_result(
        cls,
        request: HandoffAuditRequest,
        result: JudgeResult,
        *,
        audit_id: Optional[str] = None,
        stats: Optional[HandoffStats] = None,
    ) -> "HandoffAuditResponse":
        lg = request.langgraph
        if result.verdict == Verdict.PASS:
            next_node = lg.to_node
            interrupt = False
        elif result.verdict == Verdict.FAIL:
            next_node = lg.from_node
            interrupt = False
        else:
            next_node = None
            interrupt = True

        recommendations = [
            StructuredRecommendation(
                type="prompt_patch",
                title="Prompt improvement",
                description=text,
                target_node=lg.from_node,
            )
            for text in result.prompt_improvements
        ]

        weave_trace_id = request.weave.trace_id if request.weave else None

        return cls(
            audit_id=audit_id or str(uuid4()),
            result=result,
            langgraph=lg,
            next_node=next_node,
            should_interrupt=interrupt,
            recommendations=recommendations,
            handoff_stats=stats,
            weave_trace_id=weave_trace_id,
            redis=RedisRef(
                workflow_key=f"workflow:{lg.thread_id}",
                stats_key=f"stats:{lg.graph_id}:{lg.handoff_key}",
                event_channel=f"channel:workflow:{lg.thread_id}",
            ),
        )
