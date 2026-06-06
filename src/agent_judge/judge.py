"""Core judge logic.

Pipeline (each stage is a Weave op so the whole trace tree is captured):

    run_judge
      └─ run_judge_once               (one independent evaluation)
           ├─ derive_rubric           (LLM: goal -> checkable criteria)
           ├─ evaluate_rubric         (LLM: criteria vs. evidence)
           └─ aggregate_verdict       (deterministic: evaluations -> verdict)

`run_judge` optionally runs `run_judge_once` multiple times and majority-votes
the verdict (consensus mode). Aggregation is deterministic on purpose: the LLM
judges each criterion, but the pass/fail/uncertain decision and the
stop/continue signal are computed by code so orchestrators get stable behavior.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from statistics import mean
from typing import Dict, List, Tuple

import weave

from agent_judge import llm, prompts
from agent_judge.schemas import (
    CriterionEvaluation,
    CriterionStatus,
    JudgeInput,
    JudgeResult,
    RubricCriterion,
    Verdict,
)

PASS_THRESHOLD = 0.85  # weighted fraction of satisfied criteria required to pass


# --------------------------------------------------------------------------- #
# Stage 1: derive rubric
# --------------------------------------------------------------------------- #


@weave.op
def derive_rubric(data: JudgeInput) -> List[RubricCriterion]:
    """Turn the original goal + system prompt into checkable criteria."""
    result = llm.complete_json(
        system=prompts.RUBRIC_SYSTEM,
        user=prompts.rubric_user_prompt(data),
    )
    raw_items = result.get("rubric", []) or []
    rubric: List[RubricCriterion] = []
    seen_ids = set()
    for i, item in enumerate(raw_items):
        cid = str(item.get("id") or f"criterion_{i + 1}").strip()
        while cid in seen_ids:
            cid = f"{cid}_{i}"
        seen_ids.add(cid)
        rubric.append(
            RubricCriterion(
                id=cid,
                requirement=str(item.get("requirement", "")).strip(),
                weight=float(item.get("weight", 1.0) or 1.0),
                critical=bool(item.get("critical", False)),
            )
        )
    if not rubric:
        raise llm.LLMError("Rubric derivation returned no criteria.")
    return rubric


# --------------------------------------------------------------------------- #
# Stage 2: evaluate rubric against evidence
# --------------------------------------------------------------------------- #


@weave.op
def evaluate_rubric(
    data: JudgeInput, rubric: List[RubricCriterion]
) -> Tuple[List[CriterionEvaluation], List[str]]:
    """Judge each criterion strictly against the evidence."""
    rubric_json = json.dumps(
        [c.model_dump() for c in rubric], indent=2, ensure_ascii=False
    )
    result = llm.complete_json(
        system=prompts.EVAL_SYSTEM,
        user=prompts.eval_user_prompt(data, rubric_json),
    )

    by_id: Dict[str, dict] = {}
    for item in result.get("evaluations", []) or []:
        if "id" in item:
            by_id[str(item["id"])] = item

    evaluations: List[CriterionEvaluation] = []
    for crit in rubric:
        item = by_id.get(crit.id, {})
        status_raw = str(item.get("status", "unsupported")).strip().lower()
        try:
            status = CriterionStatus(status_raw)
        except ValueError:
            status = CriterionStatus.UNSUPPORTED
        evaluations.append(
            CriterionEvaluation(
                id=crit.id,
                requirement=crit.requirement,
                status=status,
                confidence=_clamp(float(item.get("confidence", 0.5) or 0.5)),
                reasoning=str(item.get("reasoning", "")).strip(),
                evidence_quote=str(item.get("evidence_quote", "")).strip(),
            )
        )

    prompt_improvements = [
        str(p).strip()
        for p in (result.get("prompt_improvements", []) or [])
        if str(p).strip()
    ]
    return evaluations, prompt_improvements


# --------------------------------------------------------------------------- #
# Stage 3: aggregate into a verdict (deterministic)
# --------------------------------------------------------------------------- #


@weave.op
def aggregate_verdict(
    rubric: List[RubricCriterion],
    evaluations: List[CriterionEvaluation],
    prompt_improvements: List[str],
) -> JudgeResult:
    """Combine per-criterion evaluations into a stop/continue verdict."""
    weight_by_id = {c.id: max(c.weight, 0.0) for c in rubric}
    critical_by_id = {c.id: c.critical for c in rubric}

    total_weight = sum(weight_by_id.values()) or 1.0
    satisfied_weight = 0.0
    not_satisfied: List[CriterionEvaluation] = []
    unsupported: List[CriterionEvaluation] = []
    critical_not_satisfied = False
    critical_unsupported = False

    for ev in evaluations:
        w = weight_by_id.get(ev.id, 1.0)
        is_critical = critical_by_id.get(ev.id, False)
        if ev.status == CriterionStatus.SATISFIED:
            satisfied_weight += w
        elif ev.status == CriterionStatus.NOT_SATISFIED:
            not_satisfied.append(ev)
            if is_critical:
                critical_not_satisfied = True
        else:  # UNSUPPORTED
            unsupported.append(ev)
            if is_critical:
                critical_unsupported = True

    ratio = satisfied_weight / total_weight

    # Decision logic.
    if critical_not_satisfied:
        verdict = Verdict.FAIL
    elif not_satisfied:
        # Any concrete, evidence-backed failure means the task is incomplete.
        verdict = Verdict.FAIL
    elif ratio >= PASS_THRESHOLD and not critical_unsupported:
        verdict = Verdict.PASS
    else:
        # Remaining gaps are claimed-but-unproven -> need more evidence.
        verdict = Verdict.UNCERTAIN

    can_continue = verdict == Verdict.PASS

    # Confidence: how decisive the per-criterion judgements were.
    individual = [ev.confidence for ev in evaluations] or [0.0]
    base_conf = mean(individual)
    if verdict == Verdict.UNCERTAIN:
        # Cap confidence when we are explicitly unsure.
        base_conf = min(base_conf, 0.6)
    confidence = _clamp(base_conf)

    missing_evidence = [ev.requirement for ev in (not_satisfied + unsupported)]
    failure_reasons: List[str] = []
    for ev in not_satisfied:
        failure_reasons.append(
            f"{ev.requirement}: {ev.reasoning or 'not satisfied by the evidence.'}"
        )
    if critical_unsupported:
        for ev in unsupported:
            if critical_by_id.get(ev.id):
                failure_reasons.append(
                    f"{ev.requirement}: claimed but not proven by the evidence "
                    "(critical)."
                )

    summary, next_action = _summarize(
        verdict, ratio, not_satisfied, unsupported
    )

    return JudgeResult(
        verdict=verdict,
        can_continue=can_continue,
        confidence=confidence,
        summary=summary,
        rubric=rubric,
        evaluations=evaluations,
        missing_evidence=missing_evidence,
        failure_reasons=failure_reasons,
        suggested_next_action=next_action,
        prompt_improvements=prompt_improvements,
        consensus_runs=1,
    )


def _summarize(
    verdict: Verdict,
    ratio: float,
    not_satisfied: List[CriterionEvaluation],
    unsupported: List[CriterionEvaluation],
) -> Tuple[str, str]:
    pct = round(ratio * 100)
    if verdict == Verdict.PASS:
        return (
            f"Handoff verified: {pct}% of weighted criteria are satisfied by the "
            "evidence and no requirements are unmet.",
            "Proceed to the next workflow step.",
        )
    if verdict == Verdict.FAIL:
        names = ", ".join(ev.requirement for ev in not_satisfied[:5]) or "key requirements"
        return (
            f"Handoff blocked: the evidence does not satisfy required criteria "
            f"({names}). Only {pct}% of weighted criteria are met.",
            "Block the handoff and return to the agent to address the missing "
            "requirements before retrying.",
        )
    # UNCERTAIN
    names = ", ".join(ev.requirement for ev in unsupported[:5]) or "several requirements"
    return (
        f"Insufficient evidence: the claim asserts completion but the evidence "
        f"does not prove {names}.",
        "Request more evidence/artifacts from the agent, then re-run the check.",
    )


# --------------------------------------------------------------------------- #
# Orchestration: single run + consensus
# --------------------------------------------------------------------------- #


@weave.op
def run_judge_once(data: JudgeInput) -> JudgeResult:
    """One full evaluation pass (rubric -> evaluate -> verdict)."""
    rubric = derive_rubric(data)
    evaluations, prompt_improvements = evaluate_rubric(data, rubric)
    return aggregate_verdict(rubric, evaluations, prompt_improvements)


@weave.op
def run_judge(data: JudgeInput, consensus_runs: int | None = None) -> JudgeResult:
    """Top-level judge entrypoint.

    If `consensus_runs` (or env JUDGE_CONSENSUS_RUNS) > 1, run multiple
    independent passes and majority-vote the verdict.
    """
    if consensus_runs is None:
        consensus_runs = _env_consensus_runs()
    consensus_runs = max(1, int(consensus_runs))

    if consensus_runs == 1:
        try:
            return run_judge_once(data)
        except llm.LLMError as exc:
            return JudgeResult.uncertain_fallback(str(exc))

    results: List[JudgeResult] = []
    for _ in range(consensus_runs):
        try:
            results.append(run_judge_once(data))
        except llm.LLMError:
            continue

    if not results:
        return JudgeResult.uncertain_fallback(
            "All consensus runs failed to produce a verdict."
        )

    return _consensus(results, consensus_runs)


def _consensus(results: List[JudgeResult], runs: int) -> JudgeResult:
    """Majority-vote the verdict; average confidence over the winning runs."""
    votes = Counter(r.verdict for r in results)
    # Tie-break order: fail > uncertain > pass (fail closed / be conservative).
    order = {Verdict.FAIL: 0, Verdict.UNCERTAIN: 1, Verdict.PASS: 2}
    winning_verdict = sorted(
        votes.items(), key=lambda kv: (-kv[1], order[kv[0]])
    )[0][0]

    winners = [r for r in results if r.verdict == winning_verdict]
    representative = max(winners, key=lambda r: r.confidence)
    representative = representative.model_copy(
        update={
            "confidence": _clamp(mean(r.confidence for r in winners)),
            "consensus_runs": runs,
            "summary": (
                f"[consensus {votes[winning_verdict]}/{len(results)}] "
                + representative.summary
            ),
        }
    )
    return representative


def _env_consensus_runs() -> int:
    try:
        return max(1, int(os.getenv("JUDGE_CONSENSUS_RUNS", "1")))
    except ValueError:
        return 1


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))
