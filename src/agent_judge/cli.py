"""Command-line wrapper around the judge.

Useful for shell pipelines and CI: the process exit code reflects the verdict
so you can `&&` the next step only when the handoff passes.

Exit codes:
    0 -> pass
    1 -> fail
    2 -> uncertain
    3 -> judge error

Examples:
    # From a JSON file matching the JudgeInput schema:
    judge-cli --input examples/data/travel_incomplete.json

    # From flags:
    judge-cli --goal "..." --claim "Done" --evidence "..."

    # Pipe just the machine-readable result:
    judge-cli --input case.json --quiet
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from agent_judge.judge import run_judge
from agent_judge.schemas import JudgeInput, JudgeResult, Verdict
from agent_judge.tracing import init_weave

EXIT_CODES = {
    Verdict.PASS: 0,
    Verdict.FAIL: 1,
    Verdict.UNCERTAIN: 2,
}


def _load_input(args: argparse.Namespace) -> JudgeInput:
    if args.input:
        raw = json.loads(Path(args.input).read_text(encoding="utf-8"))
        return JudgeInput.model_validate(raw)
    if not args.goal or not args.claim:
        raise SystemExit(
            "Provide --input <file.json>, or at least --goal and --claim."
        )
    return JudgeInput(
        original_goal=args.goal,
        agent_system_prompt=args.system_prompt or "",
        agent_claim=args.claim,
        evidence=args.evidence or "",
        workflow_context=args.context or "",
    )


def _print_human(result: JudgeResult) -> None:
    icon = {
        Verdict.PASS: "PASS",
        Verdict.FAIL: "FAIL",
        Verdict.UNCERTAIN: "UNCERTAIN",
    }[result.verdict]
    print(f"\n=== Judge verdict: {icon} (confidence {result.confidence:.2f}) ===")
    print(f"can_continue: {result.can_continue}")
    print(f"\n{result.summary}\n")

    if result.rubric:
        print("Rubric:")
        for c in result.rubric:
            flag = " [critical]" if c.critical else ""
            print(f"  - ({c.id}, w={c.weight}){flag} {c.requirement}")

    if result.evaluations:
        print("\nEvaluations:")
        for e in result.evaluations:
            print(f"  - [{e.status.value}] {e.requirement}")
            if e.reasoning:
                print(f"      reason: {e.reasoning}")

    if result.missing_evidence:
        print("\nMissing evidence:")
        for m in result.missing_evidence:
            print(f"  - {m}")

    if result.failure_reasons:
        print("\nFailure reasons:")
        for r in result.failure_reasons:
            print(f"  - {r}")

    if result.suggested_next_action:
        print(f"\nSuggested next action: {result.suggested_next_action}")

    if result.prompt_improvements:
        print("\nPrompt improvements:")
        for p in result.prompt_improvements:
            print(f"  - {p}")
    print()


def main() -> int:
    load_dotenv()
    init_weave()

    parser = argparse.ArgumentParser(
        prog="judge-cli",
        description="Verify an agent handoff with the Agent-as-Judge.",
    )
    parser.add_argument("--input", help="Path to a JSON file matching JudgeInput.")
    parser.add_argument("--goal", help="Original goal/task.")
    parser.add_argument("--claim", help="The agent's completion claim.")
    parser.add_argument("--system-prompt", help="The agent's system prompt.")
    parser.add_argument("--evidence", help="The agent's actual output/artifacts.")
    parser.add_argument("--context", help="Workflow context.")
    parser.add_argument(
        "--consensus",
        type=int,
        default=None,
        help="Number of consensus runs (overrides JUDGE_CONSENSUS_RUNS).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Only print the JSON result (machine-readable).",
    )
    args = parser.parse_args()

    try:
        data = _load_input(args)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"Failed to read input: {exc}", file=sys.stderr)
        return 3

    result = run_judge(data, consensus_runs=args.consensus)

    if args.quiet:
        print(json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False))
    else:
        _print_human(result)
        print("Machine-readable result:")
        print(json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False))

    return EXIT_CODES.get(result.verdict, 3)


if __name__ == "__main__":
    sys.exit(main())
