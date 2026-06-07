"""LangGraph travel pipeline demo with a judge gate at the Planner → Booker handoff.

Demonstrates the proposed orchestration pattern:

    planner → judge_gate → (pass) booker
                        → (fail) planner retry
                        → (uncertain) human_review

Run:
    pip install -e ".[langgraph]"
    python examples/langgraph_travel_demo.py

Requires an LLM API key. Set WEAVE_PROJECT to trace the full graph in W&B Weave.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Literal, TypedDict

import weave
from dotenv import load_dotenv

from agent_judge.audit import audit_handoff
from agent_judge.handoff_schemas import (
    EvidenceBundle,
    HandoffAuditRequest,
    LangGraphHandoffContext,
)
from agent_judge.schemas import Verdict
from agent_judge.tracing import init_weave, is_enabled

DATA = Path(__file__).parent / "data"
GRAPH_ID = "travel_pipeline_v1"
THREAD_ID = f"travel-demo-{uuid.uuid4().hex[:8]}"


class TravelState(TypedDict):
    goal: str
    system_prompt: str
    claim: str
    evidence: str
    workflow_context: str
    attempt: int
    source_file: str
    last_verdict: str
    last_summary: str
    can_continue: bool
    audit_id: str
    route: str


def _load_case(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


@weave.op
def planner_node(state: TravelState) -> TravelState:
    """Simulated planner agent — loads itinerary from fixture data."""
    case = _load_case(state["source_file"])
    return {
        **state,
        "goal": case["original_goal"],
        "system_prompt": case.get("agent_system_prompt", ""),
        "claim": case["agent_claim"],
        "evidence": case["evidence"],
        "workflow_context": case.get("workflow_context", ""),
        "route": "judge_gate",
    }


@weave.op
def judge_gate_node(state: TravelState) -> TravelState:
    """Verify the planner handoff before allowing the booker to proceed."""
    request = HandoffAuditRequest(
        langgraph=LangGraphHandoffContext(
            graph_id=GRAPH_ID,
            thread_id=THREAD_ID,
            from_node="planner",
            to_node="booker",
            attempt=state["attempt"],
        ),
        original_goal=state["goal"],
        agent_claim=state["claim"],
        agent_system_prompt=state["system_prompt"],
        workflow_context=state["workflow_context"],
        evidence=EvidenceBundle(output=state["evidence"]),
    )
    response = audit_handoff(request)
    verdict = response.result.verdict.value
    route = "end"
    if verdict == Verdict.PASS.value:
        route = "booker"
    elif verdict == Verdict.UNCERTAIN.value:
        route = "human_review"

    return {
        **state,
        "last_verdict": verdict,
        "last_summary": response.result.summary,
        "can_continue": response.result.can_continue,
        "audit_id": response.audit_id,
        "route": route,
    }


@weave.op
def booker_node(state: TravelState) -> TravelState:
    """Downstream agent — only reached when the judge passes the handoff."""
    return {**state, "route": "done"}


@weave.op
def human_review_node(state: TravelState) -> TravelState:
    """Placeholder for CopilotKit HITL when the judge returns uncertain."""
    return {**state, "route": "done"}


def _route_after_judge(
    state: TravelState,
) -> Literal["booker", "human_review", "end"]:
    route = state.get("route", "human_review")
    if route == "booker":
        return "booker"
    if route == "human_review":
        return "human_review"
    return "end"


def _route_after_planner(_state: TravelState) -> Literal["judge_gate"]:
    return "judge_gate"


def build_graph():
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(TravelState)
    graph.add_node("planner", planner_node)
    graph.add_node("judge_gate", judge_gate_node)
    graph.add_node("booker", booker_node)
    graph.add_node("human_review", human_review_node)

    graph.add_edge(START, "planner")
    graph.add_conditional_edges("planner", _route_after_planner, {"judge_gate": "judge_gate"})
    graph.add_conditional_edges(
        "judge_gate",
        _route_after_judge,
        {
            "booker": "booker",
            "human_review": "human_review",
            "end": END,
        },
    )
    graph.add_edge("booker", END)
    graph.add_edge("human_review", END)
    return graph.compile()


def main() -> None:
    load_dotenv()
    init_weave()

    print("Agent-as-Judge :: LangGraph travel handoff demo")
    if is_enabled():
        print("Weave tracing: ENABLED")
    else:
        print("Weave tracing: disabled (set WEAVE_PROJECT + WANDB_API_KEY)")

    app = build_graph()

    # Attempt 1: incomplete itinerary → expect fail → retry
    state: TravelState = {
        "goal": "",
        "system_prompt": "",
        "claim": "",
        "evidence": "",
        "workflow_context": "",
        "attempt": 1,
        "source_file": "travel_incomplete.json",
        "last_verdict": "",
        "last_summary": "",
        "can_continue": False,
        "audit_id": "",
        "route": "",
    }

    print("\n--- Attempt 1 (incomplete itinerary) ---")
    result = app.invoke(state)
    print(f"Verdict: {result['last_verdict'].upper()}")
    print(f"Summary: {result['last_summary']}")
    print(f"Audit ID: {result['audit_id']}")

    if result["last_verdict"] != Verdict.FAIL.value:
        print("[!] Expected FAIL on incomplete output.")

    # Attempt 2: corrected itinerary → expect pass → booker
    print("\n--- Attempt 2 (corrected itinerary) ---")
    retry: TravelState = {
        **result,
        "attempt": 2,
        "source_file": "travel_corrected.json",
    }
    final = app.invoke(retry)
    print(f"Verdict: {final['last_verdict'].upper()}")
    print(f"Summary: {final['last_summary']}")
    print(f"Can continue to booker: {final['can_continue']}")

    if final["last_verdict"] == Verdict.PASS.value:
        print("\n--> Handoff approved. Booker node reached.")
    else:
        print("\n[!] Expected PASS on corrected output.")

    print("\nDone.")


if __name__ == "__main__":
    main()
