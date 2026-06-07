import { EventType, type BaseEvent, type RunAgentInput } from "@ag-ui/core";
import { BuiltInAgent, CopilotRuntime, createCopilotRuntimeHandler } from "@copilotkit/runtime/v2";

const copilotModel = process.env.COPILOTKIT_MODEL ?? "openai/gpt-4.1-mini";
const agentRelayPrompt = [
  "You are Agent Relay Copilot inside a multi-agent handoff audit dashboard.",
  "Help builders connect agent flows, understand why a downstream agent is paused, inspect agent prompts, and call frontend tools to load replays, connect flows, select agents, or send proof requests.",
  "Use plain language for designers, PMs, founders, and engineers. Focus on the current handoff: what the upstream agent claimed, what proof is missing, why the next agent is paused, and what action fixes it.",
].join(" ");

const judgeAgent = hasProviderKey(copilotModel)
  ? new BuiltInAgent({
      model: copilotModel,
      maxSteps: 3,
      temperature: 0.2,
      prompt: agentRelayPrompt,
    })
  : new BuiltInAgent({
      type: "custom",
      factory: ({ input }) => agentRelayFallbackStream(input),
    });

const runtime = new CopilotRuntime({
  agents: {
    default: judgeAgent,
  },
});

const handler = createCopilotRuntimeHandler({
  runtime,
  basePath: "/api/copilotkit",
});

export const GET = handler;
export const POST = handler;
export const OPTIONS = handler;

function hasProviderKey(model: string) {
  if (model.startsWith("openai/")) return Boolean(process.env.OPENAI_API_KEY?.trim());
  if (model.startsWith("anthropic/")) return Boolean(process.env.ANTHROPIC_API_KEY?.trim());
  if (model.startsWith("google/")) return Boolean(process.env.GOOGLE_API_KEY?.trim());
  return Boolean(
    process.env.OPENAI_API_KEY?.trim() ||
      process.env.ANTHROPIC_API_KEY?.trim() ||
      process.env.GOOGLE_API_KEY?.trim(),
  );
}

async function* agentRelayFallbackStream(input: RunAgentInput): AsyncIterable<BaseEvent> {
  const messageId = crypto.randomUUID();
  const text = buildFallbackReply(input);

  yield {
    type: EventType.TEXT_MESSAGE_START,
    messageId,
    role: "assistant",
  };

  for (const chunk of chunkText(text)) {
    yield {
      type: EventType.TEXT_MESSAGE_CONTENT,
      messageId,
      delta: chunk,
    };
  }

  yield {
    type: EventType.TEXT_MESSAGE_END,
    messageId,
  };
}

function buildFallbackReply(input: RunAgentInput) {
  const message = latestUserText(input).toLowerCase();

  if (message.includes("connect")) {
    return "Connect the upstream agent at the handoff point: send Agent Relay the original goal, the agent claim, evidence, from_node, and to_node. In this demo, the Connect panel shows the exact audit_handoff payload shape.";
  }

  if (message.includes("patch") || message.includes("prompt")) {
    return "Prompt patch: before handoff, require the agent to return a proof table mapping every user requirement to evidence, mark missing fields explicitly, and only claim done when the proof table is complete.";
  }

  if (message.includes("booker") || message.includes("paused") || message.includes("pause")) {
    return "Booker is paused because Planner claimed the trip was complete, but the evidence does not prove the budget math or flights yet.";
  }

  return "Agent Relay checks the handoff before the next agent acts: what the agent claims, what the evidence proves, what is missing, and the smallest action that unlocks the flow.";
}

function latestUserText(input: RunAgentInput) {
  const message = [...input.messages].reverse().find((item) => item.role === "user");
  if (!message) return "";
  if (typeof message.content === "string") return message.content;
  return message.content
    .filter((part) => part.type === "text")
    .map((part) => part.text)
    .join(" ");
}

function chunkText(text: string) {
  const words = text.split(" ");
  const chunks: string[] = [];

  for (let index = 0; index < words.length; index += 7) {
    chunks.push(`${words.slice(index, index + 7).join(" ")} `);
  }

  return chunks;
}
