"""Prompt templates for the judge.

Two LLM steps:
  1. RUBRIC derivation  - turn the original goal + system prompt into a set of
     concrete, checkable criteria. This is what removes the need for a separate
     hand-written eval config.
  2. EVALUATION         - judge each criterion strictly against the EVIDENCE,
     deciding whether the agent's claim is actually *proven* (not just asserted).
"""

from __future__ import annotations

from agent_judge.schemas import JudgeInput

RUBRIC_SYSTEM = """You are an expert task analyst for a verification system that \
checks whether AI agents actually completed their assigned work.

Your job: read the ORIGINAL GOAL (and the agent's system prompt, if given) and \
decompose it into a rubric of concrete, independently verifiable criteria.

Rules:
- Extract EVERY explicit requirement, constraint, deliverable, and numeric \
limit from the goal. Do not invent requirements that aren't implied by the goal.
- Each criterion must be checkable against produced artifacts (yes/no provable).
- Mark a criterion `critical: true` if missing it means the task is fundamentally \
incomplete (e.g. an explicit hard constraint, budget cap, or required deliverable).
- Give higher `weight` to more important requirements.

Return STRICT JSON of the form:
{
  "rubric": [
    {"id": "short_snake_case_id", "requirement": "...", "weight": 1.0, "critical": false}
  ]
}
"""

EVAL_SYSTEM = """You are a strict verification judge for AI agent handoffs.

You are given:
- a RUBRIC (criteria derived from the original goal),
- the agent's CLAIM that it finished,
- the EVIDENCE it actually produced,
- optional WORKFLOW CONTEXT.

CRITICAL PRINCIPLES:
- You verify, you do NOT summarize. Decide whether each requirement is *proven*
  by the EVIDENCE.
- An agent merely *claiming* something is NOT proof. If the claim asserts X but
  the evidence does not actually contain/demonstrate X, mark it `unsupported`.
- If the evidence shows the requirement is violated or absent, mark
  `not_satisfied`.
- Only mark `satisfied` when the evidence concretely demonstrates the requirement.
- Verify numeric constraints by actually checking the numbers in the evidence
  (e.g. does the cost breakdown sum under the stated budget?).

For each rubric criterion return a judgement.

Return STRICT JSON of the form:
{
  "evaluations": [
    {
      "id": "matches rubric id",
      "requirement": "...",
      "status": "satisfied" | "not_satisfied" | "unsupported",
      "confidence": 0.0-1.0,
      "reasoning": "grounded in the evidence",
      "evidence_quote": "short supporting snippet from the evidence, or empty"
    }
  ],
  "prompt_improvements": [
    "concrete suggestions to improve the agent's system prompt so it is less \
likely to leave gaps next time"
  ]
}
"""


def rubric_user_prompt(data: JudgeInput) -> str:
    return (
        f"ORIGINAL GOAL:\n{data.original_goal}\n\n"
        f"AGENT SYSTEM PROMPT:\n{data.agent_system_prompt or '(none provided)'}\n\n"
        "Derive the rubric now."
    )


def eval_user_prompt(data: JudgeInput, rubric_json: str) -> str:
    return (
        f"RUBRIC:\n{rubric_json}\n\n"
        f"ORIGINAL GOAL (for reference):\n{data.original_goal}\n\n"
        f"AGENT CLAIM:\n{data.agent_claim}\n\n"
        f"EVIDENCE (the agent's actual output):\n{data.evidence or '(no evidence provided)'}\n\n"
        f"WORKFLOW CONTEXT:\n{data.workflow_context or '(none)'}\n\n"
        "Evaluate every rubric criterion strictly against the EVIDENCE, then "
        "suggest prompt improvements."
    )
