# Agent-as-Judge

**A Judge MCP server that verifies agent handoffs in multi-agent workflows.**

Multi-agent pipelines fail silently when one agent *claims* a task is done and
the next agent trusts that claim without checking. Agent-as-Judge sits at those
handoff points: any agent can call the judge with the original goal, its
completion claim, and the evidence it produced. The judge derives a rubric from
the goal, checks whether the claim is actually *proven* by the evidence, and
returns a structured `pass` / `fail` / `uncertain` verdict your orchestrator can
act on automatically.

Every judge execution is traced end-to-end in [W&B Weave](https://wandb.ai/site/weave).

---

## Why agent-handoff verification matters

In a pipeline like `Planner -> Booker -> Notifier`, the Booker assumes the
Planner's "Done!" is true. If the plan is missing flights or busts the budget,
the failure propagates silently and is expensive to debug later. A judge at the
handoff:

- **Blocks bad handoffs** (`fail`) before they corrupt downstream steps.
- **Requests more evidence** (`uncertain`) when a claim can't be verified.
- **Allows good handoffs** (`pass`) to proceed automatically.

The judge does **not** summarize the agent's work. It decides whether the
completion claim is supported by the evidence.

---

## How it works

```
run_judge
  └─ run_judge_once
       ├─ derive_rubric      LLM: original goal -> concrete, weighted criteria
       ├─ evaluate_rubric    LLM: each criterion vs. the evidence (satisfied / not / unsupported)
       └─ aggregate_verdict  code: criteria -> pass / fail / uncertain + can_continue
```

- The **rubric is generated automatically** from the original goal, so you don't
  maintain a separate eval config per task.
- The **final decision is deterministic code**, so orchestrators get stable
  stop/continue behavior even though an LLM does the per-criterion judging.
- An optional **consensus mode** runs the judge N times and majority-votes.

### Verdict semantics

| verdict | `can_continue` | meaning |
|---|---|---|
| `pass` | `true` | The next workflow step may proceed. |
| `fail` | `false` | Block the handoff; a requirement is demonstrably unmet. |
| `uncertain` | `false` | Request more evidence, then re-check. |

---

## Install

Requires Python 3.10+.

```bash
pip install -e .
cp .env.example .env   # then fill in your keys
```

Set at least one LLM key in `.env`:

```bash
JUDGE_LLM_PROVIDER=openai          # or "anthropic"
OPENAI_API_KEY=sk-...
# optional: JUDGE_MODEL, ANTHROPIC_API_KEY, JUDGE_CONSENSUS_RUNS
```

## CopilotKit UI

This repo also includes a Next.js LLM Judge workbench in [`app/`](app). It gives
you an editable judge surface for prompts, reference answers, rubrics, candidate
responses, score breakdowns, and a CopilotKit sidebar that can inspect the judge
state and run frontend tools.

```bash
npm install
cp .env.example .env.local   # then fill in OPENAI_API_KEY
npm run dev
```

Open `http://localhost:3000`.

The CopilotKit runtime is served from `/api/copilotkit` and uses
`COPILOTKIT_MODEL` when set, defaulting to `openai/gpt-4.1-mini`.

---

## Run the MCP server

```bash
judge-mcp                     # console script
# or
python -m agent_judge.server
```

The server speaks MCP over **stdio**, so it works with Claude Desktop, Cursor,
or any MCP client. Inspect it interactively:

```bash
npx -y @modelcontextprotocol/inspector judge-mcp
```

### Register with an MCP client

```json
{
  "mcpServers": {
    "agent-judge": {
      "command": "judge-mcp",
      "env": {
        "JUDGE_LLM_PROVIDER": "openai",
        "OPENAI_API_KEY": "sk-...",
        "WEAVE_PROJECT": "agent-judge",
        "WANDB_API_KEY": "..."
      }
    }
  }
}
```

---

## Call `judge_handoff`

The tool accepts:

| field | required | description |
|---|---|---|
| `original_goal` | yes | The task the agent was given (source of truth). |
| `agent_claim` | yes | The agent's completion claim. |
| `agent_system_prompt` | no | The prompt/role the agent ran under. |
| `evidence` | no | The agent's actual output/artifacts (the claim is checked against this). |
| `workflow_context` | no | Context about the surrounding workflow. |

It returns structured JSON:

```json
{
  "verdict": "fail",
  "can_continue": false,
  "confidence": 0.86,
  "summary": "Handoff blocked: the evidence does not satisfy required criteria ...",
  "rubric": [ { "id": "flights", "requirement": "...", "weight": 2.0, "critical": true } ],
  "evaluations": [ { "id": "flights", "status": "not_satisfied", "reasoning": "..." } ],
  "missing_evidence": ["Flight costs", "Total cost breakdown", "Dietary constraints"],
  "failure_reasons": ["Flights: no flight costs appear in the itinerary."],
  "suggested_next_action": "Block the handoff and return to the agent ...",
  "prompt_improvements": ["Require an itemized cost table that sums to a total ..."]
}
```

### From the CLI

The CLI exits with a verdict-based status code (`0` pass, `1` fail, `2`
uncertain, `3` error), so it drops straight into shell pipelines and CI:

```bash
judge-cli --input examples/data/travel_incomplete.json
judge-cli --input examples/data/travel_corrected.json --quiet

# gate the next step on a passing handoff
judge-cli --input case.json && ./run-next-step.sh
```

### From Python

```python
from agent_judge import run_judge, JudgeInput

result = run_judge(JudgeInput(
    original_goal="Plan a 5-day Tokyo trip for a family of four under $6,000 ...",
    agent_claim="Done. I created a complete itinerary under $6,000.",
    evidence="<the itinerary the agent produced>",
))
if result.can_continue:
    proceed()
else:
    print(result.failure_reasons)
```

---

## Travel demo

The primary demo runs the full loop end to end:

```bash
python examples/travel_demo.py
```

1. **Goal** — Plan a 5-day Tokyo trip for a family of four under $6,000
   (flights, lodging, daily activities, dietary constraints, total breakdown).
2. **Incomplete output** — an itinerary with activities and lodging but **no
   flights, no total budget, and ignored dietary needs** -> judge returns
   **`fail`** and lists the missing requirements.
3. **Corrected output** — adds flight costs, dietary-aware meals, and a summed
   budget of $5,720 -> judge returns **`pass`** and the workflow may proceed.

Data lives in [`examples/data/`](examples/data).

---

## Eval examples

```bash
python examples/run_evals.py
```

Three guard cases keep the judge honest:

- **false positive** ([`eval_false_positive.json`](examples/data/eval_false_positive.json)) —
  task is incomplete; judge must **not** say `pass`.
- **false negative** ([`eval_false_negative.json`](examples/data/eval_false_negative.json)) —
  task is genuinely complete; judge must **not** wrongly reject it.
- **uncertain** ([`eval_uncertain.json`](examples/data/eval_uncertain.json)) —
  evidence is too thin to verify; judge must return `uncertain`.

The harness exits non-zero if any case doesn't match its expected verdict.

---

## W&B Weave tracing

Tracing is a first-class feature, not an afterthought. Each judge stage is a
Weave op (`@weave.op`), so a single `judge_handoff` call produces a full trace
tree:

```
run_judge
└─ run_judge_once
   ├─ derive_rubric        (inputs + the derived rubric)
   ├─ evaluate_rubric      (each per-criterion evaluation; nested LLM calls)
   └─ aggregate_verdict    (final verdict, confidence, prompt improvements)
```

Because the OpenAI/Anthropic SDK calls are auto-instrumented by Weave, the raw
LLM requests/responses appear nested under the right op automatically.

Enable it by setting `WEAVE_PROJECT` (and being logged into wandb):

```bash
WEAVE_PROJECT=agent-judge
WANDB_API_KEY=...
```

If `WEAVE_PROJECT` is unset, tracing degrades to a no-op and the judge still
runs locally — so first-run is frictionless.

---

## Project structure

```
src/agent_judge/
  schemas.py     Pydantic input/output models (the contract)
  llm.py         provider-agnostic JSON LLM client (OpenAI / Anthropic)
  prompts.py     rubric-derivation + evaluation prompts
  judge.py       derive_rubric / evaluate_rubric / aggregate_verdict / run_judge
  tracing.py     init_weave() (graceful no-op when unconfigured)
  server.py      FastMCP server exposing judge_handoff (stdio)
  cli.py         CLI wrapper with verdict-based exit codes
examples/
  travel_demo.py incomplete -> fail, corrected -> pass
  run_evals.py   false-positive / false-negative / uncertain guards
  data/          goal + agent outputs + eval cases
```

## License

MIT
