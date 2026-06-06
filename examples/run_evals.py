"""Basic eval harness for the judge.

Runs three guard cases and checks the judge produces the expected verdict:

  - false_positive_guard : task is incomplete -> judge must FAIL (not pass)
  - false_negative_guard : task is complete   -> judge must PASS (not reject)
  - uncertain_guard      : evidence too thin  -> judge must be UNCERTAIN

Run:
    python examples/run_evals.py

Exit code is 0 only if every case matches its expected verdict. Each judge run
is traced in Weave when WEAVE_PROJECT is configured.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from agent_judge.judge import run_judge
from agent_judge.schemas import JudgeInput
from agent_judge.tracing import init_weave

DATA = Path(__file__).parent / "data"

CASES = [
    "eval_false_positive.json",
    "eval_false_negative.json",
    "eval_uncertain.json",
]


def main() -> int:
    load_dotenv()
    init_weave()

    print("Agent-as-Judge :: eval harness\n")
    passed = 0
    for filename in CASES:
        raw = json.loads((DATA / filename).read_text(encoding="utf-8"))
        expected = raw.get("expected_verdict")
        data = JudgeInput.model_validate(
            {k: v for k, v in raw.items()
             if k in JudgeInput.model_fields}
        )
        result = run_judge(data)
        ok = result.verdict.value == expected
        passed += int(ok)

        status = "OK  " if ok else "MISS"
        print(f"[{status}] {raw.get('name', filename)}")
        print(f"        expected={expected}  got={result.verdict.value}  "
              f"(confidence {result.confidence:.2f})")
        print(f"        {result.summary}\n")

    total = len(CASES)
    print(f"Result: {passed}/{total} cases matched expected verdicts.")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
