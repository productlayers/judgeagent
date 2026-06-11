# Agent-as-Judge

**A verification agent for multi-agent pipelines.**

Multi-agent pipelines fail silently when one agent claims a task is done and the next trusts that claim without checking. Agent-as-Judge sits at those handoff points: pass it the original goal, the agent's claim, and its evidence — it derives a rubric from the goal, checks whether the claim is proven by the evidence, and returns a structured `pass` / `fail` / `uncertain` verdict the orchestrator can act on.

Every execution is traced end-to-end in [W&B Weave](https://wandb.ai/site/weave).

**[Demo video](https://www.youtube.com/watch?v=rNQsqGtMVWM) · [Slides](https://docs.google.com/presentation/d/1PkxEazN4Akwa_UQ3lMdfg80WSMjGhYNk/edit?slide=id.p1#slide=id.p1)**

---

## Why handoff verification

In a pipeline like `Planner -> Booker -> Notifier`, the Booker assumes the Planner's "Done!" is true. If the plan is missing flights or busts the budget, the failure propagates silently and is expensive to debug. A judge at the handoff:

- **Blocks bad handoffs** (`fail`) before they corrupt downstream steps.
- **Requests more evidence** (`uncertain`) when a claim can't be verified.
- **Allows good handoffs** (`pass`) to proceed.

The judge doesn't summarize the agent's work — it decides whether the completion claim is supported by the evidence.

---

## How it works

```
run_judge
  └─ run_judge_once
       ├─ derive_rubric      LLM: original goal -> concrete, weighted criteria
       ├─ evaluate_rubric    LLM: each criterion vs. the evidence (satisfied / not / unsupported)
       └─ aggregate_verdict  code: criteria -> pass / fail / uncertain + can_continue
```

The rubric is generated from the goal — no manual eval config per task. The final verdict is deterministic code, so the stop/continue signal is stable even though an LLM does the per-criterion judging. Consensus mode runs the judge N times and majority-votes.

### Verdict semantics

| verdict | `can_continue` | meaning |
|---|---|---|
| `pass` | `true` | Proceed to the next step. |
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

A Next.js judge workbench lives in [`app/`](app) — editable prompts, rubrics, candidate responses, score breakdowns, and a CopilotKit sidebar that can inspect judge state and run frontend tools.

```bash
npm install
cp .env.example .env.local   # then fill in OPENAI_API_KEY
npm run dev
```

Open `http://localhost:3000`. The CopilotKit runtime is served from `/api/copilotkit` and uses `COPILOTKIT_MODEL` when set, defaulting to `openai/gpt-4.1-mini`.

---

## Run the MCP server

```bash
judge-mcp                     # console script
# or
python -m agent_judge.server
```

The server speaks MCP over **stdio** — works with Claude Desktop, Cursor, or any MCP client. Inspect it interactively:

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

| field | required | description |
|---|---|---|
| `original_goal` | yes | The task the agent was given (source of truth). |
| `agent_claim` | yes | The agent's completion claim. |
| `agent_system_prompt` | no | The prompt/role the agent ran under. |
| `evidence` | no | The agent's actual output/artifacts. |
| `workflow_context` | no | Context about the surrounding workflow. |

Returns structured JSON:

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

The CLI exits with a verdict-based status code (`0` pass, `1` fail, `2` uncertain, `3` error):

```bash
judge-cli --input examples/data/travel_incomplete.json
judge-cli --input examples/data/travel_corrected.json --quiet

# gate the next step on a passing handoff
judge-cli --input case.json && ./run-next-step.sh
```

### From Python

```python
from agent_judge import run_judge, audit_handoff, JudgeInput, HandoffAuditRequest
from agent_judge.handoff_schemas import EvidenceBundle, LangGraphHandoffContext

# Core judge (any orchestrator)
result = run_judge(JudgeInput(
    original_goal="Plan a 5-day Tokyo trip for a family of four under $6,000 ...",
    agent_claim="Done. I created a complete itinerary under $6,000.",
    evidence="<the itinerary the agent produced>",
))

# LangGraph-aware audit (routing hints + stats + Weave/Redis refs)
response = audit_handoff(HandoffAuditRequest(
    langgraph=LangGraphHandoffContext(
        graph_id="travel_pipeline_v1",
        thread_id="demo-thread-1",
        from_node="planner",
        to_node="booker",
    ),
    original_goal="...",
    agent_claim="Done.",
    evidence=EvidenceBundle(output="..."),
))
if response.result.can_continue:
    proceed_to(response.next_node)
elif response.should_interrupt:
    request_human_review()
else:
    retry_node(response.next_node)
```

---

## LangGraph demo

**Planner → Judge gate → Booker**

```bash
pip install -e ".[langgraph]"
python examples/langgraph_travel_demo.py
```

Each graph node is a Weave op. The judge gate calls `audit_handoff()` with evidence from graph state — no agent re-run. On `fail`, the orchestrator retries; on `pass`, the booker runs.

---

## Travel demo

```bash
python examples/travel_demo.py
```

1. **Goal** — 5-day Tokyo trip, family of four, under $6,000 (flights, lodging, activities, dietary constraints, total breakdown).
2. **Incomplete output** — itinerary with activities and lodging, no flights, no budget, ignored dietary needs → judge returns `fail` with the missing requirements.
3. **Corrected output** — adds flights, dietary-aware meals, total of $5,720 → judge returns `pass`.

Data lives in [`examples/data/`](examples/data).

---

## Eval guards

```bash
python examples/run_evals.py
```

Three cases keep the judge honest:

- **false positive** — task incomplete; judge must not say `pass`.
- **false negative** — task complete; judge must not wrongly reject.
- **uncertain** — evidence too thin; judge must return `uncertain`.

The harness exits non-zero if any case doesn't match its expected verdict.

---

## W&B Weave tracing

Each judge stage is a Weave op, so a single `judge_handoff` call produces a full trace tree:

```
run_judge
└─ run_judge_once
   ├─ derive_rubric        (inputs + derived rubric)
   ├─ evaluate_rubric      (per-criterion evaluations + nested LLM calls)
   └─ aggregate_verdict    (final verdict, confidence, prompt improvements)
```

OpenAI/Anthropic SDK calls are auto-instrumented — raw LLM requests appear nested under the right op automatically.

Enable by setting `WEAVE_PROJECT` in `.env`. Without it, tracing is a no-op and the judge still runs locally.

```bash
pip install -e ".[dev]"
pytest
```

---

## Project structure

```
src/agent_judge/
  schemas.py          Pydantic input/output models (the contract)
  handoff_schemas.py  LangGraph + evidence bundle + audit response models
  audit.py            audit_handoff() — routing hints, stats, Weave op
  llm.py              provider-agnostic JSON LLM client (OpenAI / Anthropic)
  prompts.py          rubric-derivation + evaluation prompts
  judge.py            derive_rubric / evaluate_rubric / aggregate_verdict / run_judge
  tracing.py          init_weave() (graceful no-op when unconfigured)
  server.py           FastMCP: judge_handoff + audit_handoff tools
  cli.py              CLI wrapper with verdict-based exit codes
examples/
  travel_demo.py              incomplete -> fail, corrected -> pass
  langgraph_travel_demo.py    LangGraph Planner -> Judge gate -> Booker
  run_evals.py                false-positive / false-negative / uncertain guards
  data/                       goal + agent outputs + eval cases
tests/                        aggregate, handoff audit, weave tracing
app/                          CopilotKit judge workbench (Next.js)
docs/                         architecture doc
```

## License

MIT
