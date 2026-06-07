"""FastMCP server exposing the `judge_handoff` tool.

Run it:
    judge-mcp                     # console script (after `pip install -e .`)
    python -m agent_judge.server  # module form

The server speaks MCP over stdio, so it plugs into Claude Desktop, Cursor, the
MCP Inspector, or any custom MCP client.
"""

from __future__ import annotations

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from agent_judge.audit import audit_handoff
from agent_judge.handoff_schemas import (
    EvidenceBundle,
    HandoffAuditRequest,
    HandoffAuditResponse,
    LangGraphHandoffContext,
)
from agent_judge.judge import run_judge
from agent_judge.schemas import JudgeInput, JudgeResult
from agent_judge.tracing import init_weave

load_dotenv()
init_weave()

mcp = FastMCP("agent-judge")


@mcp.tool(
    name="judge_handoff",
    annotations={
        "title": "Judge an agent handoff",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
def judge_handoff(
    original_goal: str,
    agent_claim: str,
    agent_system_prompt: str = "",
    evidence: str = "",
    workflow_context: str = "",
) -> JudgeResult:
    """Verify whether an agent's completion claim is actually supported.

    Derives an evaluation rubric from the original goal, checks the agent's
    claim against the available evidence, and returns a structured verdict that
    an orchestrator can use to stop or continue the workflow.

    Args:
        original_goal: The original task/goal the agent was given (source of truth).
        agent_claim: The agent's completion claim (e.g. "Done, I created ...").
        agent_system_prompt: The system prompt the agent operated under (optional).
        evidence: The actual artifacts/output produced by the agent (optional but
            strongly recommended; the claim is checked against this).
        workflow_context: Context about the surrounding workflow (optional).

    Returns:
        JudgeResult with:
          - verdict: "pass" | "fail" | "uncertain"
          - can_continue: True only when verdict == "pass"
          - confidence: 0-1
          - summary, rubric, evaluations
          - missing_evidence, failure_reasons
          - suggested_next_action, prompt_improvements

    Stop/continue semantics:
          - pass      -> next workflow step may proceed (can_continue=True)
          - fail      -> block the handoff (can_continue=False)
          - uncertain -> request more evidence before proceeding (can_continue=False)
    """
    data = JudgeInput(
        original_goal=original_goal,
        agent_system_prompt=agent_system_prompt,
        agent_claim=agent_claim,
        evidence=evidence,
        workflow_context=workflow_context,
    )
    return run_judge(data)


@mcp.tool(
    name="audit_handoff",
    annotations={
        "title": "Audit a LangGraph handoff",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
def audit_handoff_tool(
    graph_id: str,
    thread_id: str,
    from_node: str,
    to_node: str,
    original_goal: str,
    agent_claim: str,
    agent_system_prompt: str = "",
    evidence: str = "",
    workflow_context: str = "",
    attempt: int = 1,
    checkpoint_id: str = "",
    weave_trace_id: str = "",
    weave_project: str = "",
) -> HandoffAuditResponse:
    """Audit a LangGraph handoff with orchestration metadata and routing hints.

    Same verification as ``judge_handoff``, plus ``next_node``, ``should_interrupt``,
    structured recommendations, Redis key refs, and rolling handoff stats.

    Returns HandoffAuditResponse with the full JudgeResult nested under ``result``.
    """
    weave_ref = None
    if weave_trace_id and weave_project:
        from agent_judge.handoff_schemas import WeaveRef

        weave_ref = WeaveRef(project=weave_project, trace_id=weave_trace_id)

    request = HandoffAuditRequest(
        langgraph=LangGraphHandoffContext(
            graph_id=graph_id,
            thread_id=thread_id,
            from_node=from_node,
            to_node=to_node,
            attempt=attempt,
            checkpoint_id=checkpoint_id or None,
        ),
        original_goal=original_goal,
        agent_claim=agent_claim,
        agent_system_prompt=agent_system_prompt,
        workflow_context=workflow_context,
        evidence=EvidenceBundle(output=evidence),
        weave=weave_ref,
    )
    return audit_handoff(request)


def main() -> None:
    """Console-script entrypoint: run the MCP server over stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
