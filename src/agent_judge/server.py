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


def main() -> None:
    """Console-script entrypoint: run the MCP server over stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
