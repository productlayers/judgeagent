import { BuiltInAgent, CopilotRuntime, createCopilotRuntimeHandler } from "@copilotkit/runtime/v2";

const judgeAgent = new BuiltInAgent({
  model: process.env.COPILOTKIT_MODEL ?? "openai/gpt-4.1-mini",
  maxSteps: 3,
  temperature: 0.2,
  prompt: [
    "You are an LLM-as-judge assistant inside an evaluation workbench.",
    "Help users refine rubrics, compare candidate answers, and call frontend tools when the user asks you to update scores or load examples.",
    "Be precise, cite the rubric criteria you are using, and separate correctness, completeness, safety, and style observations.",
  ].join(" "),
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
