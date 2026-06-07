import type { Metadata } from "next";
import { AgentRelayCopilotProvider } from "./copilotkit-client";
import "@copilotkit/react-core/v2/styles.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "Agent Relay",
  description: "Audit multi-agent handoffs before the next agent acts.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <AgentRelayCopilotProvider>{children}</AgentRelayCopilotProvider>
      </body>
    </html>
  );
}
