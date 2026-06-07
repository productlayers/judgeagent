// @ts-nocheck
"use client";

// CopilotKit v2's root package currently trips Next 16's client-boundary
// handling because it re-exports upstream packages with `export *`. Import the
// compiled client bundle directly so provider, sidebar, and hooks share the
// same internal React context while avoiding that boundary file.
import type { ReactNode } from "react";
import {
  J as useConfigureSuggestions,
  at as useAgentContext,
  it as CopilotKitProvider,
  tt as useFrontendTool,
  y as CopilotSidebar,
} from "../node_modules/@copilotkit/react-core/dist/copilotkit-DEGlMWM0.mjs";

export { CopilotSidebar, useAgentContext, useConfigureSuggestions, useFrontendTool };

export function AgentRelayCopilotProvider({ children }: { children: ReactNode }) {
  return (
    <CopilotKitProvider runtimeUrl="/api/copilotkit" showDevConsole="auto" useSingleEndpoint={false}>
      {children}
    </CopilotKitProvider>
  );
}
