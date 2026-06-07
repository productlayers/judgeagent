"""Handoff audit service — LangGraph-aware wrapper around the core judge."""

from __future__ import annotations

from typing import Optional

import weave

from agent_judge.handoff_schemas import (
    HandoffAuditRequest,
    HandoffAuditResponse,
    HandoffStats,
)
from agent_judge.judge import run_judge
from agent_judge.schemas import JudgeResult, Verdict

# In-process stats store (Redis replacement for local dev / tests).
_HANDOFF_STATS: dict[str, HandoffStats] = {}


def _stats_key(request: HandoffAuditRequest) -> str:
    lg = request.langgraph
    return f"{lg.graph_id}:{lg.handoff_key}"


def _record_stats(request: HandoffAuditRequest, result: JudgeResult) -> HandoffStats:
    key = _stats_key(request)
    stats = _HANDOFF_STATS.get(key, HandoffStats())
    stats.total += 1
    if result.verdict == Verdict.PASS:
        stats.pass_count += 1
    elif result.verdict == Verdict.FAIL:
        stats.fail_count += 1
    else:
        stats.uncertain_count += 1
    _HANDOFF_STATS[key] = stats
    return stats


def get_handoff_stats(graph_id: str, handoff_key: str) -> HandoffStats:
    """Return rolling stats for a handoff edge (in-process; swap for Redis in prod)."""
    return _HANDOFF_STATS.get(f"{graph_id}:{handoff_key}", HandoffStats())


def reset_handoff_stats() -> None:
    """Clear in-process stats (for tests)."""
    _HANDOFF_STATS.clear()


@weave.op
def audit_handoff(
    request: HandoffAuditRequest,
    *,
    consensus_runs: Optional[int] = None,
) -> HandoffAuditResponse:
    """Audit a LangGraph handoff using historical evidence from the request.

    Wraps ``run_judge`` and adds routing hints (``next_node``, ``should_interrupt``),
    structured recommendations, Redis key refs, and rolling handoff stats.
    """
    result = run_judge(request.to_judge_input(), consensus_runs=consensus_runs)
    stats = _record_stats(request, result)
    return HandoffAuditResponse.from_judge_result(request, result, stats=stats)
