import { NextResponse } from "next/server";

type HandoffPayload = {
  graph_id?: string;
  thread_id?: string;
  from_node?: string;
  to_node?: string;
  original_goal?: string;
  agent_claim?: string;
  evidence?: string;
  trace_id?: string;
};

export async function GET() {
  return NextResponse.json({
    name: "Agent Relay handoff intake",
    description:
      "POST goal, claim, evidence, and handoff metadata here to connect an agent flow to the dashboard demo.",
    required_fields: ["original_goal", "agent_claim", "evidence", "from_node", "to_node"],
    mcp_tool: "audit_handoff",
  });
}

export async function POST(request: Request) {
  const body = (await request.json()) as HandoffPayload;
  const auditId = `audit_${Date.now()}`;
  const missing = ["original_goal", "agent_claim", "evidence", "from_node", "to_node"].filter(
    (field) => !body[field as keyof HandoffPayload],
  );

  return NextResponse.json({
    audit_id: auditId,
    status: missing.length ? "received_with_missing_fields" : "received",
    missing_fields: missing,
    graph_id: body.graph_id ?? "connected_flow",
    thread_id: body.thread_id ?? body.trace_id ?? auditId,
    handoff: {
      from: body.from_node ?? "upstream_agent",
      to: body.to_node ?? "downstream_agent",
    },
    dashboard_message:
      "Handoff received. In the full runtime this payload is passed to audit_handoff, streamed through Redis, and shown in the Agent Relay dashboard.",
  });
}
