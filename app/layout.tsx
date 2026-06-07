import type { Metadata } from "next";
import { CopilotKit } from "@copilotkit/react-core/v2";
import "@copilotkit/react-core/v2/styles.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "LLM Judge",
  description: "A CopilotKit-powered workbench for evaluating LLM responses.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <CopilotKit runtimeUrl="/api/copilotkit" showDevConsole>
          {children}
        </CopilotKit>
      </body>
    </html>
  );
}
