"use client";

import { useMemo, useState } from "react";
import {
  CopilotSidebar,
  useAgentContext,
  useConfigureSuggestions,
  useFrontendTool,
} from "./copilotkit-client";
import {
  Bot,
  Cable,
  CheckCircle2,
  CirclePause,
  ClipboardList,
  Code2,
  Database,
  Eye,
  FileText,
  GitBranch,
  Link2,
  Play,
  RefreshCw,
  Send,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { ToolCallStatus } from "@copilotkit/core";
import { z } from "zod";

type AgentStatus = "complete" | "selected" | "checking" | "paused" | "idle";

type AgentNode = {
  id: string;
  name: string;
  label: string;
  role: string;
  prompt: string;
  tools: string[];
  status: AgentStatus;
  lastClaim: string;
  lastOutput: string;
  promptGap: string;
  suggestedPatch: string;
};

type Flow = {
  name: string;
  source: "Trace replay" | "MCP" | "HTTP API";
  evidenceSource: string;
  traceId: string;
  fromAgentId: string;
  toAgentId: string;
  goal: string;
  claim: string;
  currentCheck: string;
  pausedReason: string;
  missingProof: string[];
  recommendedAction: string;
  suggestedMessage: string;
  agents: AgentNode[];
  events: string[];
};

const travelFlow: Flow = {
  name: "Travel Planner",
  source: "Trace replay",
  evidenceSource: "LangGraph state + saved output",
  traceId: "travel-demo-42",
  fromAgentId: "planner",
  toAgentId: "booker",
  goal:
    "Plan a 5-day Tokyo trip under $6,000 with flights, lodging, activities, dietary needs, and a complete budget.",
  claim: "I created the complete trip plan.",
  currentCheck: "Agent Relay is checking whether Planner's evidence proves the original request before Booker runs.",
  pausedReason: "Booker is paused because the plan does not prove the budget and flights yet.",
  missingProof: ["Budget math is missing", "Flights are missing"],
  recommendedAction: "Ask Planner for a proof package, then retry only Planner.",
  suggestedMessage:
    "Please return flights and a budget table that proves the trip stays under the limit before Booker runs.",
  agents: [
    {
      id: "request",
      name: "Trip request",
      label: "Request",
      role: "Original user request",
      prompt: "Plan a 5-day Tokyo trip under $6,000 with flights, lodging, activities, dietary needs, and a complete budget.",
      tools: ["Goal"],
      status: "complete",
      lastClaim: "The user asked for a complete trip plan.",
      lastOutput: "Source of truth for the audit.",
      promptGap: "None. This is the original request.",
      suggestedPatch: "No patch needed.",
    },
    {
      id: "planner",
      name: "Planner",
      label: "Planner",
      role: "Creates a trip plan from the request.",
      prompt:
        "Plan the trip with flights, lodging, activities, food needs, and budget.",
      tools: ["Search", "Itinerary builder"],
      status: "selected",
      lastClaim: "I created the complete trip plan.",
      lastOutput: "Itinerary present, proof package incomplete.",
      promptGap: "It asks for a plan, but not explicit proof that every requirement is satisfied.",
      suggestedPatch:
        "Before handoff, return an evidence table with flights, budget arithmetic, dietary coverage, and unmet constraints.",
    },
    {
      id: "judge",
      name: "Agent Relay check",
      label: "Check",
      role: "Verifies the handoff before the next agent acts.",
      prompt:
        "Derive requirements from the original goal, check the agent claim against evidence, then return pass, fail, or uncertain.",
      tools: ["audit_handoff", "Redis Stream", "Weave trace"],
      status: "checking",
      lastClaim: "Planner says the plan is complete.",
      lastOutput: "Budget and flights are not proven by the evidence.",
      promptGap: "No gap. This node is doing the verification.",
      suggestedPatch: "Keep this gate between Planner and Booker.",
    },
    {
      id: "booker",
      name: "Booker",
      label: "Booker",
      role: "Books the trip only after the plan is verified.",
      prompt:
        "Book approved travel plans only when the handoff includes complete verified inputs.",
      tools: ["Booking API", "Payment hold"],
      status: "paused",
      lastClaim: "Waiting for verified plan.",
      lastOutput: "Paused before acting on incomplete information.",
      promptGap: "Booker needs a verified budget and flight details before it can proceed.",
      suggestedPatch:
        "Require an Agent Relay pass result before using Planner output.",
    },
  ],
  events: [
    "Travel trace loaded",
    "Planner claim received",
    "Agent Relay checking evidence",
    "Booker paused",
    "Missing-proof action ready",
  ],
};

const customFlowDefaults = {
  flowName: "My Agent Flow",
  fromAgent: "Researcher",
  toAgent: "Writer",
  evidenceSource: "Agent output + tool calls",
  traceId: "trace-001",
};

function makeConnectedFlow(draft = customFlowDefaults): Flow {
  const fromId = draft.fromAgent.toLowerCase().replace(/[^a-z0-9]+/g, "-") || "agent-a";
  const toId = draft.toAgent.toLowerCase().replace(/[^a-z0-9]+/g, "-") || "agent-b";

  return {
    name: draft.flowName || "Connected Agent Flow",
    source: "MCP",
    evidenceSource: draft.evidenceSource || "Agent output + tool calls",
    traceId: draft.traceId || "trace-001",
    fromAgentId: fromId,
    toAgentId: toId,
    goal: "Audit the selected handoff when the upstream agent says it is done.",
    claim: `${draft.fromAgent || "Upstream agent"} says its work is ready for ${draft.toAgent || "the next agent"}.`,
    currentCheck: "Agent Relay is ready to check the next handoff payload this flow sends.",
    pausedReason: "The next agent stays paused until the first handoff is checked.",
    missingProof: ["Waiting for first handoff evidence", "Waiting for agent claim"],
    recommendedAction: "Call audit_handoff at the handoff point with goal, claim, and evidence.",
    suggestedMessage:
      "Send the original goal, the agent's claim, and the produced evidence when this handoff occurs.",
    agents: [
      {
        id: fromId,
        name: draft.fromAgent || "Upstream agent",
        label: draft.fromAgent || "Agent A",
        role: "Completes work and hands evidence to the next agent.",
        prompt: "Paste this agent's prompt here when connecting a live flow.",
        tools: ["Your tools"],
        status: "selected",
        lastClaim: "Waiting for first claim.",
        lastOutput: "Waiting for first evidence bundle.",
        promptGap: "Unknown until the first audit runs.",
        suggestedPatch: "After the first audit, Agent Relay will suggest a prompt patch.",
      },
      {
        id: "judge",
        name: "Agent Relay check",
        label: "Check",
        role: "Verifies the handoff before the next agent acts.",
        prompt: "Check goal, claim, and evidence. Route pass, fail, or uncertain.",
        tools: ["audit_handoff", "Redis Stream", "Weave trace"],
        status: "checking",
        lastClaim: "Waiting for first handoff.",
        lastOutput: "No audit result yet.",
        promptGap: "No gap. This is the verification node.",
        suggestedPatch: "Keep this gate at the risky handoff.",
      },
      {
        id: toId,
        name: draft.toAgent || "Downstream agent",
        label: draft.toAgent || "Agent B",
        role: "Acts only after Agent Relay verifies the handoff.",
        prompt: "Use upstream output only after a passing handoff.",
        tools: ["Your downstream tools"],
        status: "paused",
        lastClaim: "Waiting for a verified handoff.",
        lastOutput: "Paused until Agent Relay passes the handoff.",
        promptGap: "Should require a pass result before acting.",
        suggestedPatch: "Add a guard: do not run unless Agent Relay returns pass.",
      },
    ],
    events: [
      "Flow linked",
      "Waiting for handoff payload",
      "Redis stream ready",
    ],
  };
}

function statusLabel(status: AgentStatus) {
  if (status === "complete") return "Done";
  if (status === "selected") return "Clicked";
  if (status === "checking") return "Checking now";
  if (status === "paused") return "Paused";
  return "Waiting";
}

function statusIcon(status: AgentStatus) {
  if (status === "paused") return <CirclePause size={15} />;
  if (status === "checking") return <ShieldCheck size={15} />;
  if (status === "complete") return <CheckCircle2 size={15} />;
  return <Bot size={15} />;
}

async function postHandoffIntake(flow: Flow) {
  const upstream =
    flow.agents.find((agent) => agent.id === flow.fromAgentId) ?? flow.agents[0];
  const downstream =
    flow.agents.find((agent) => agent.id === flow.toAgentId) ?? flow.agents[flow.agents.length - 1];

  try {
    const response = await fetch("/api/audit/handoff", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        graph_id: flow.name.toLowerCase().replace(/[^a-z0-9]+/g, "_"),
        thread_id: flow.traceId,
        from_node: upstream.name,
        to_node: downstream.name,
        original_goal: flow.goal,
        agent_claim: flow.claim,
        evidence: flow.evidenceSource,
        trace_id: flow.traceId,
      }),
    });
    const payload = (await response.json()) as { status?: string; audit_id?: string };
    return `Intake ${payload.status ?? "received"}: ${payload.audit_id ?? "audit queued"}`;
  } catch {
    return "Flow connected locally. Intake API will receive handoffs when the dev server is running.";
  }
}

export default function JudgeWorkbench() {
  const [flow, setFlow] = useState<Flow>(travelFlow);
  const [draft, setDraft] = useState(customFlowDefaults);
  const [selectedAgentId, setSelectedAgentId] = useState("planner");
  const [copilotAction, setCopilotAction] = useState("Missing-proof action ready");

  const selectedAgent =
    flow.agents.find((agent) => agent.id === selectedAgentId) ?? flow.agents[0];
  const upstreamAgent =
    flow.agents.find((agent) => agent.id === flow.fromAgentId) ?? flow.agents[0];
  const downstreamAgent =
    flow.agents.find((agent) => agent.id === flow.toAgentId) ?? flow.agents[flow.agents.length - 1];

  const callSnippet = useMemo(
    () =>
      JSON.stringify(
        {
          graph_id: flow.name.toLowerCase().replace(/[^a-z0-9]+/g, "_"),
          thread_id: flow.traceId,
          from_node: upstreamAgent.name,
          to_node: downstreamAgent.name,
          original_goal: "<what the user asked for>",
          agent_claim: "<what the agent says is done>",
          evidence: "<the actual output, tool calls, or artifacts>",
        },
        null,
        2,
      ),
    [downstreamAgent.name, flow.name, flow.traceId, upstreamAgent.name],
  );

  useAgentContext({
    description:
      "Agent Relay dashboard state for auditing multi-agent handoffs. Includes the connected flow, selected agent, current claim, missing proof, recommended fix, and handoff API snippet.",
    value: {
      flow,
      selectedAgent,
      upstreamAgent,
      downstreamAgent,
      copilotAction,
      callSnippet,
    },
  });

  useConfigureSuggestions(
    {
      suggestions: [
        {
          title: "Explain the pause",
          message: `Explain why ${downstreamAgent.name} is paused and what would unlock it.`,
        },
        {
          title: "Patch the prompt",
          message: `Patch ${selectedAgent.name}'s prompt so the next handoff has proof.`,
        },
        {
          title: "Connect my flow",
          message: "Connect a Researcher to Writer handoff and tell me where to call audit_handoff.",
        },
      ],
    },
    [downstreamAgent.name, selectedAgent.name],
  );

  useFrontendTool(
    {
      name: "loadTravelReplay",
      description: "Load the prebuilt travel-planner handoff replay.",
      parameters: z.object({}),
      handler: async () => {
        setFlow(travelFlow);
        setSelectedAgentId("planner");
        setCopilotAction("Travel replay loaded");
        return "Loaded the travel-planner replay. Planner is selected and Booker is paused.";
      },
      render: ({
        status,
        result,
      }: {
        status: ToolCallStatus;
        result?: string;
      }) => (
        <div className="tool-result">
          <Play size={16} />
          <span>{status === ToolCallStatus.Complete ? result : "Loading travel replay..."}</span>
        </div>
      ),
    },
    [],
  );

  useFrontendTool(
    {
      name: "connectAgentFlow",
      description: "Connect a custom two-agent handoff flow to the Agent Relay dashboard.",
      parameters: z.object({
        flowName: z.string().describe("The flow name, such as Support Triage."),
        fromAgent: z.string().describe("The upstream agent that claims work is done."),
        toAgent: z.string().describe("The downstream agent that waits for verified input."),
        evidenceSource: z
          .string()
          .optional()
          .describe("Where evidence comes from, such as tool calls or trace output."),
      }),
      handler: async ({
        flowName,
        fromAgent,
        toAgent,
        evidenceSource,
      }: {
        flowName: string;
        fromAgent: string;
        toAgent: string;
        evidenceSource?: string;
      }) => {
        const nextDraft = {
          flowName,
          fromAgent,
          toAgent,
          evidenceSource: evidenceSource || "Agent output + tool calls",
          traceId: `${flowName.toLowerCase().replace(/[^a-z0-9]+/g, "-") || "flow"}-trace`,
        };
        const nextFlow = makeConnectedFlow(nextDraft);
        const intake = await postHandoffIntake(nextFlow);
        setDraft(nextDraft);
        setFlow(nextFlow);
        setSelectedAgentId(nextFlow.fromAgentId);
        setCopilotAction(intake);
        return `Connected ${fromAgent} -> ${toAgent}. ${intake}`;
      },
      render: ({
        args,
        status,
        result,
      }: {
        args: { fromAgent?: string; toAgent?: string };
        status: ToolCallStatus;
        result?: string;
      }) => (
        <div className="tool-result">
          <Cable size={16} />
          <span>
            {status === ToolCallStatus.Complete
              ? result
              : `Connecting ${args.fromAgent ?? "agent"} -> ${args.toAgent ?? "agent"}...`}
          </span>
        </div>
      ),
    },
    [],
  );

  useFrontendTool(
    {
      name: "selectAgent",
      description: "Select an agent in the Agent Relay flow so its details are shown.",
      parameters: z.object({
        agentName: z.string().describe("Agent name to select, such as Planner or Booker."),
      }),
      handler: async ({ agentName }: { agentName: string }) => {
        const agent = flow.agents.find(
          (item) =>
            item.name.toLowerCase() === agentName.toLowerCase() ||
            item.label.toLowerCase() === agentName.toLowerCase(),
        );
        if (!agent) return `I could not find an agent named ${agentName}.`;
        setSelectedAgentId(agent.id);
        setCopilotAction(`Selected ${agent.name}`);
        return `Selected ${agent.name}.`;
      },
    },
    [flow.agents],
  );

  useFrontendTool(
    {
      name: "sendProofRequest",
      description: "Create the recommended proof request for the upstream agent.",
      parameters: z.object({}),
      handler: async () => {
        setCopilotAction("Proof request sent to upstream agent");
        setFlow((current) => ({
          ...current,
          events: [...current.events, "Proof request sent"],
        }));
        return flow.suggestedMessage;
      },
      render: ({
        status,
        result,
      }: {
        status: ToolCallStatus;
        result?: string;
      }) => (
        <div className="tool-result">
          <Send size={16} />
          <span>{status === ToolCallStatus.Complete ? result : "Preparing proof request..."}</span>
        </div>
      ),
    },
    [flow.suggestedMessage],
  );

  async function connectDraftFlow() {
    const nextFlow = makeConnectedFlow(draft);
    const intake = await postHandoffIntake(nextFlow);
    setFlow(nextFlow);
    setSelectedAgentId(nextFlow.fromAgentId);
    setCopilotAction(intake);
  }

  function loadTravelReplay() {
    setFlow(travelFlow);
    setSelectedAgentId("planner");
    setCopilotAction("Travel replay loaded");
  }

  return (
    <main className="agent-relay-shell">
      <section className="agent-relay-hero" aria-label="Agent Relay overview">
        <div>
          <div className="eyebrow">
            <ShieldCheck size={15} />
            Agent Relay
          </div>
          <h1>Your agent says it is done. Agent Relay checks before the next agent acts.</h1>
        </div>
        <div className="live-pill">
          <span />
          Redis live replay
        </div>
      </section>

      <section className="connect-panel" aria-label="Connect agent flow">
        <div className="connect-copy">
          <div className="eyebrow blue">
            <Link2 size={15} />
            Connect your agent flow
          </div>
          <h2>{flow.name} is linked through audit_handoff</h2>
          <p>
            Use the travel replay for the demo, or connect a new handoff so builders can see where to call the judge.
          </p>
        </div>

        <div className="connect-form">
          <label>
            <span>Flow</span>
            <input value={draft.flowName} onChange={(event) => setDraft({ ...draft, flowName: event.target.value })} />
          </label>
          <label>
            <span>Hands off from</span>
            <input value={draft.fromAgent} onChange={(event) => setDraft({ ...draft, fromAgent: event.target.value })} />
          </label>
          <label>
            <span>Hands off to</span>
            <input value={draft.toAgent} onChange={(event) => setDraft({ ...draft, toAgent: event.target.value })} />
          </label>
          <button className="primary-button" type="button" onClick={connectDraftFlow}>
            <Cable size={17} />
            Connect
          </button>
          <button className="ghost-button" type="button" onClick={loadTravelReplay}>
            <Play size={17} />
            Travel demo
          </button>
        </div>

        <div className="connect-snippet">
          <div>
            <Code2 size={16} />
            <span>Call this when an agent says done</span>
          </div>
          <pre>{callSnippet}</pre>
        </div>
      </section>

      <section className="flow-card" aria-label="Flow being checked">
        <div className="section-heading">
          <div>
            <div className="eyebrow">
              <GitBranch size={15} />
              Flow being checked
            </div>
            <h2>
              {upstreamAgent.name} -&gt; Agent Relay check -&gt; {downstreamAgent.name}
            </h2>
          </div>
          <div className="status-chip">
            <Database size={16} />
            {flow.traceId}
          </div>
        </div>

        <div className="flow-line">
          {flow.agents.map((agent, index) => (
            <div className="flow-step-wrap" key={agent.id}>
              {index > 0 ? <div className={`flow-connector ${agent.status === "paused" ? "paused" : ""}`} /> : null}
              <button
                className={`flow-step ${agent.status} ${selectedAgentId === agent.id ? "active" : ""}`}
                type="button"
                onClick={() => setSelectedAgentId(agent.id)}
              >
                <span>{statusIcon(agent.status)}</span>
                <small>{statusLabel(agent.status)}</small>
                <strong>{agent.label}</strong>
              </button>
            </div>
          ))}
        </div>
      </section>

      <section className="story-grid" aria-label="Audit story">
        <article className="story-card">
          <div className="eyebrow blue">
            <Bot size={15} />
            What is happening
          </div>
          <h2>{upstreamAgent.name} says the work is ready.</h2>
          <div className="claim-box">
            <span>Agent claim</span>
            <strong>"{flow.claim}"</strong>
          </div>
          <p>{flow.currentCheck}</p>
        </article>

        <article className="story-card blocked">
          <div className="eyebrow red">
            <CirclePause size={15} />
            Why {downstreamAgent.name} is paused
          </div>
          <h2>The handoff is not safe yet.</h2>
          <div className="proof-list">
            {flow.missingProof.map((item) => (
              <div key={item}>
                <CirclePause size={15} />
                <span>{item}</span>
              </div>
            ))}
          </div>
          <p>{flow.pausedReason}</p>
        </article>

        <article className="story-card fix">
          <div className="eyebrow green">
            <Sparkles size={15} />
            What can fix it
          </div>
          <h2>{flow.recommendedAction}</h2>
          <div className="message-box">"{flow.suggestedMessage}"</div>
          <div className="action-row">
            <button className="primary-button" type="button" onClick={() => setCopilotAction("Proof request sent")}>
              <Send size={17} />
              Send
            </button>
            <button className="ghost-button" type="button" onClick={() => setCopilotAction("Retry queued")}>
              <RefreshCw size={17} />
              Retry
            </button>
            <button className="ghost-button" type="button" onClick={() => setCopilotAction("Guard saved")}>
              <ClipboardList size={17} />
              Save guard
            </button>
          </div>
        </article>
      </section>

      <section className="details-grid" aria-label="Agent and stream details">
        <aside className="agent-drawer">
          <div className="section-heading compact">
            <div>
              <div className="eyebrow">
                <Eye size={15} />
                Agent details
              </div>
              <h2>{selectedAgent.name}</h2>
            </div>
            <span className={`mini-status ${selectedAgent.status}`}>{statusLabel(selectedAgent.status)}</span>
          </div>

          <div className="detail-block">
            <span>Role</span>
            <p>{selectedAgent.role}</p>
          </div>
          <div className="detail-block">
            <span>Prompt</span>
            <p>{selectedAgent.prompt}</p>
          </div>
          <div className="detail-block">
            <span>Tools</span>
            <p>{selectedAgent.tools.join(", ")}</p>
          </div>
          <div className="detail-block">
            <span>Last claim</span>
            <p>{selectedAgent.lastClaim}</p>
          </div>
          <div className="detail-block">
            <span>Last output</span>
            <p>{selectedAgent.lastOutput}</p>
          </div>
          <div className="detail-block warning">
            <span>Prompt gap</span>
            <p>{selectedAgent.promptGap}</p>
          </div>
          <div className="detail-block">
            <span>Suggested patch</span>
            <p>{selectedAgent.suggestedPatch}</p>
          </div>
          <div className="drawer-actions">
            <button className="primary-button" type="button" onClick={() => setCopilotAction(`Prompt patch ready for ${selectedAgent.name}`)}>
              <Sparkles size={17} />
              Patch prompt
            </button>
            <button className="ghost-button" type="button" onClick={() => setCopilotAction(`Trace opened for ${selectedAgent.name}`)}>
              <FileText size={17} />
              View trace
            </button>
          </div>
        </aside>

        <aside className="stream-panel">
          <div className="section-heading compact">
            <div>
              <div className="eyebrow red">
                <Database size={15} />
                Redis stream
              </div>
              <h2>Live audit replay</h2>
            </div>
          </div>
          <div className="event-list">
            {flow.events.map((event) => (
              <div key={event}>
                <span />
                <p>{event}</p>
              </div>
            ))}
            <div>
              <span />
              <p>{copilotAction}</p>
            </div>
          </div>
        </aside>
      </section>

      <CopilotSidebar
        agentId="default"
        defaultOpen={false}
        width={430}
        labels={{
          modalHeaderTitle: "Agent Relay Copilot",
          chatInputPlaceholder: "Ask to explain a pause, patch a prompt, or connect a flow...",
          welcomeMessageText:
            "I can inspect this audit, select agents, connect your flow, and turn missing proof into the next action.",
        }}
      />
    </main>
  );
}
