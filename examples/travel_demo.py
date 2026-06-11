"""Travel-agent demo for Agent-as-Judge.

Shows the full handoff-verification loop:

    1. Original travel goal
    2. An INCOMPLETE travel-agent output  -> judge returns FAIL (handoff blocked)
    3. A CORRECTED travel-agent output    -> judge returns PASS (handoff proceeds)

Run:
    python examples/travel_demo.py

Requires an LLM API key (see .env.example). If WEAVE_PROJECT is configured,
every judge run shows up as a trace in W&B Weave.
"""

from __future__ import annotations

import json
from pathlib import Path

from dotenv import load_dotenv

from agent_judge.judge import run_judge
from agent_judge.schemas import JudgeInput, JudgeResult, Verdict
from agent_judge.tracing import init_weave, is_enabled

DATA = Path(__file__).parent / "data"


def _load(name: str) -> JudgeInput:
    raw = json.loads((DATA / name).read_text(encoding="utf-8"))
    return JudgeInput.model_validate(raw)


def _load_goal(name: str) -> str:
    raw = json.loads((DATA / name).read_text(encoding="utf-8"))
    return str(raw.get("original_goal", "")).strip()


def _show(title: str, result: JudgeResult) -> None:
    bar = "=" * 70
    print(f"\n{bar}\n{title}\n{bar}")
    print(f"VERDICT: {result.verdict.value.upper()}  "
          f"(confidence {result.confidence:.2f}, can_continue={result.can_continue})")
    print(f"\n{result.summary}")
    if result.failure_reasons:
        print("\nWhy it failed:")
        for r in result.failure_reasons:
            print(f"  - {r}")
    if result.missing_evidence:
        print("\nMissing evidence:")
        for m in result.missing_evidence:
            print(f"  - {m}")
    print(f"\nSuggested next action: {result.suggested_next_action}")
    if result.prompt_improvements:
        print("\nPrompt improvements:")
        for p in result.prompt_improvements:
            print(f"  - {p}")


def main() -> None:
    load_dotenv()
    init_weave()

    print("Agent-as-Judge :: Travel-planning handoff demo")
    if is_enabled():
        print("Weave tracing: ENABLED (check your W&B project for traces)")
    else:
        print("Weave tracing: disabled (set WEAVE_PROJECT + WANDB_API_KEY to enable)")

    goal = _load_goal("travel_goal.json")
    print(f"\nGOAL:\n{goal}")

    # --- Step 1: incomplete output -> expect FAIL ---
    incomplete = _load("travel_incomplete.json")
    print(f"\nAGENT CLAIM (attempt 1): {incomplete.agent_claim}")
    fail_result = run_judge(incomplete)
    _show("JUDGE ON INCOMPLETE OUTPUT", fail_result)

    if fail_result.verdict == Verdict.PASS:
        print("\n[!] Demo expectation: the incomplete output should NOT pass.")

    print("\n--> Handoff blocked. Agent revises its output...\n")

    # --- Step 2: corrected output -> expect PASS ---
    corrected = _load("travel_corrected.json")
    print(f"AGENT CLAIM (attempt 2): {corrected.agent_claim}")
    pass_result = run_judge(corrected)
    _show("JUDGE ON CORRECTED OUTPUT", pass_result)

    if pass_result.verdict == Verdict.PASS:
        print("\n--> Handoff approved. Workflow may proceed to the booking agent.")
    else:
        print("\n[!] Demo expectation: the corrected output should pass.")

    print("\nDone.")


if __name__ == "__main__":
    main()
