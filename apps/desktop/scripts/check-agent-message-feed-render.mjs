import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";

import React from "react";
import { AIMessage, ToolMessage } from "@langchain/core/messages";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer as createViteServer } from "vite";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const desktopRoot = path.join(repoRoot, "apps/desktop");

const vite = await createViteServer({ root: desktopRoot, appType: "custom", server: { middlewareMode: true }, logLevel: "error" });
try {
  const { AgentMessageFeed } = await vite.ssrLoadModule("/src/renderer/AgentMessageFeed.tsx");
  const messages = [
    {
      id: "ai_partial",
      content: [
        { type: "text", text: "Answer with [safe](https://example.com) and [unsafe](javascript:alert(1)).\n\n```ts\nconst ok = true;\n```" },
        { type: "reasoning", reasoning: "Provider supplied reasoning only." },
        { type: "image", source: "chart.png" },
        { type: "tool_call", name: "search", args: { q: "agent" }, status: "completed", result: "Tool result text" },
        { type: "text", text: "<script>alert('x')</script>" },
      ],
      getType() {
        return "ai";
      },
    },
  ];
  const html = renderToStaticMarkup(
    React.createElement(AgentMessageFeed, {
      messages,
      incompleteMessageIds: new Set(["ai_partial"]),
    }),
  );

  assert.match(html, /aria-label="Incomplete response"[^>]*>Partial</);
  assert.match(html, /<details class="message-reasoning"><summary>Reasoning<\/summary>/);
  assert.ok(html.includes("Provider supplied reasoning only."), "reasoning text should be preserved");
  assert.ok(!html.slice(0, html.indexOf('<details class="message-reasoning"')).includes("Provider supplied reasoning only."), "reasoning must not be mixed into answer markdown");
  assert.ok(html.includes("Image attachment: chart.png"), "image blocks should leave a visible attachment marker");
  assert.ok(html.includes("Tool result text"), "tool block results should render");
  assert.ok(html.includes("completed"), "tool block status should render");
  assert.ok(html.includes('aria-label="Copy code block"'), "fenced code blocks should expose a copy button");
  assert.ok(!html.includes("<script>"), "raw HTML script tags must not render as elements");
  assert.ok(!html.includes('href="javascript:alert(1)"'), "unsafe javascript links must not render as links");
  const historical = renderToStaticMarkup(React.createElement(AgentMessageFeed, {messages: [
    new AIMessage({id: "saved-call", content: "", tool_calls: [{id: "call-old", name: "lookup", args: {q: "retained"}}]}),
    new ToolMessage({id: "saved-result", tool_call_id: "call-old", name: "lookup", content: "Saved lookup result"}),
  ]}));
  assert.ok(historical.includes("lookup") && historical.includes("retained"), "public contentBlocks must preserve hydrated tool calls without live tool events");
  assert.ok(historical.includes("Saved lookup result") && historical.includes("Tool: lookup"));
} finally {
  await vite.close();
}

console.log("AgentMessageFeed semantic Markdown/rendering checks passed.");
