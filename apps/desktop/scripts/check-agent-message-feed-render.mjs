import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";

import React from "react";
import { AIMessage, HumanMessage, ToolMessage } from "@langchain/core/messages";
import { renderToStaticMarkup } from "react-dom/server";
import { act, create } from "react-test-renderer";
import { createServer as createViteServer } from "vite";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const desktopRoot = path.join(repoRoot, "apps/desktop");

const vite = await createViteServer({ root: desktopRoot, appType: "custom", server: { middlewareMode: true, hmr: false }, logLevel: "error" });

function findByClass(root, className) {
  return root.findAll((node) => node.props?.className === className)[0];
}

function detailsOpen(root, className) {
  const details = findByClass(root, className);
  assert.ok(details, `${className} details should render`);
  const summary = details.findByType("summary");
  return summary.props["aria-expanded"] === true;
}

async function toggleDetails(root, className, open) {
  const details = findByClass(root, className);
  assert.ok(details, `${className} details should render`);
  assert.notEqual(detailsOpen(root, className), open, `${className} details should start in the opposite state before this toggle`);
  const summary = details.findByType("summary");
  await act(async () => {
    summary.props.onClick({ preventDefault() {} });
    await tick();
  });
}

function tick() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

try {
  const { AgentMessageFeed } = await vite.ssrLoadModule("/src/renderer/AgentMessageFeed.tsx");
  const retainedInput = new HumanMessage({ id: "retained-input", content: "Source retained file: sample.txt\nAsset id: internal-id\nSHA-256: internal-hash\nsource bytes" });
  const retainedHtml = renderToStaticMarkup(React.createElement(AgentMessageFeed, {
    messages: [retainedInput],
    userMessageText: message => message.id === "retained-input" ? "" : undefined,
    renderMessageFooter: () => React.createElement("span", null, "sample.txt"),
  }));
  assert.match(retainedHtml, /sample.txt/, "attachment-only user turn retains its file card");
  assert.doesNotMatch(retainedHtml, /internal-id|internal-hash|source bytes/, "hydrated execution source labels stay out of readable user message");
  assert.match(String(retainedInput.content), /source bytes/, "display customization must not mutate execution messages");
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
  assert.match(html, /<details class="message-reasoning"><summary aria-expanded="false">Reasoning<\/summary>/);
  assert.ok(html.includes("Provider supplied reasoning only."), "reasoning text should be preserved");
  assert.ok(!html.slice(0, html.indexOf('<details class="message-reasoning"')).includes("Provider supplied reasoning only."), "reasoning must not be mixed into answer markdown");
  assert.ok(html.includes("Image attachment: chart.png"), "image blocks should leave a visible attachment marker");
  assert.ok(html.includes("Tool result text"), "tool block results should render inside activity details");
  assert.ok(html.includes("completed"), "tool block status should render");
  assert.ok(html.includes('aria-label="Copy code block"'), "fenced code blocks should expose a copy button");
  assert.ok(!html.includes("<script>"), "raw HTML script tags must not render as elements");
  assert.ok(!html.includes('href="javascript:alert(1)"'), "unsafe javascript links must not render as links");

  const detailed = renderToStaticMarkup(React.createElement(AgentMessageFeed, { messages, detailedStreams: true }));
  assert.match(detailed, /<details class="message-reasoning" open=""><summary aria-expanded="true">Reasoning<\/summary>/);
  assert.match(detailed, /<details class="message-tools" open=""><summary aria-expanded="true">Tool activity \(1\)<\/summary>/);

  const historical = renderToStaticMarkup(React.createElement(AgentMessageFeed, {messages: [
    new AIMessage({id: "saved-call", content: "", tool_calls: [{id: "call-old", name: "lookup", args: {q: "retained"}}]}),
    new ToolMessage({id: "saved-result", tool_call_id: "call-old", name: "lookup", content: "Saved lookup result"}),
  ]}));
  assert.ok(historical.includes("lookup") && historical.includes("retained"), "public contentBlocks must preserve hydrated tool calls without live tool events");
  assert.ok(historical.includes("Tool: lookup") && historical.includes("Tool activity (1)"), "tool messages should render compact activity by default");
  const historicalDetailsIndex = historical.indexOf('<details class="message-tools"');
  assert.ok(historicalDetailsIndex > -1, "compact tool result should be behind expandable details");
  assert.ok(!historical.slice(0, historicalDetailsIndex).includes("Saved lookup result"), "tool result text must not dump into the foreground when details are off");

  const errorTool = renderToStaticMarkup(React.createElement(AgentMessageFeed, {messages: [
    new ToolMessage({id: "saved-error", tool_call_id: "call-error", name: "write_file", content: "Error: write failed"}),
  ]}));
  const errorDetailsIndex = errorTool.indexOf('<details class="message-tools"');
  assert.ok(errorTool.slice(0, errorDetailsIndex).includes("Error: write failed"), "tool errors should stay visible even when details are compact");

  const growingMessage = (reasoning) => [
    {
      id: "streaming-answer",
      content: [
        { type: "text", text: "Visible answer keeps streaming." },
        { type: "reasoning", reasoning },
      ],
      getType() {
        return "ai";
      },
    },
  ];
  let renderer;
  await act(async () => {
    renderer = create(React.createElement(AgentMessageFeed, { messages: growingMessage("first thought") }));
  });
  assert.equal(detailsOpen(renderer.root, "message-reasoning"), false, "reasoning details default closed when detailed streams are off");
  await toggleDetails(renderer.root, "message-reasoning", true);
  assert.equal(detailsOpen(renderer.root, "message-reasoning"), true, "user can open reasoning details");
  await act(async () => {
    renderer.update(React.createElement(AgentMessageFeed, { messages: growingMessage("first thought\nsecond thought") }));
  });
  assert.equal(detailsOpen(renderer.root, "message-reasoning"), true, "open reasoning state should survive content growth");
  await toggleDetails(renderer.root, "message-reasoning", false);
  await act(async () => {
    renderer.update(React.createElement(AgentMessageFeed, { messages: growingMessage("final thought") }));
  });
  assert.equal(detailsOpen(renderer.root, "message-reasoning"), false, "closed reasoning state should survive content growth");

  let detailedRenderer;
  await act(async () => {
    detailedRenderer = create(React.createElement(AgentMessageFeed, { messages: growingMessage("default visible"), detailedStreams: true }));
  });
  assert.equal(detailsOpen(detailedRenderer.root, "message-reasoning"), true, "detailedStreams opens new sections by default");
  await toggleDetails(detailedRenderer.root, "message-reasoning", false);
  await act(async () => {
    detailedRenderer.update(React.createElement(AgentMessageFeed, { messages: growingMessage("still user controlled"), detailedStreams: true }));
  });
  assert.equal(detailsOpen(detailedRenderer.root, "message-reasoning"), false, "user close wins over detailedStreams preference while the section identity is stable");
  await act(async () => { renderer.unmount(); detailedRenderer.unmount(); });

  const scrolls = [];
  const listeners = new Map();
  class Transcript {
    scrollHeight = 1000;
    scrollTop = 600;
    clientHeight = 400;
    closest() { return this; }
    contains(node) { return node === this; }
    addEventListener(name, handler) { listeners.set(name, handler); }
    removeEventListener(name) { listeners.delete(name); }
    scrollTo(options) { scrolls.push(options); }
  }
  const transcript = new Transcript();
  let selected = false;
  let reduced = true;
  globalThis.HTMLElement = Transcript;
  globalThis.window = { matchMedia: () => ({ matches: reduced }) };
  globalThis.document = { getSelection: () => ({ isCollapsed: !selected, anchorNode: transcript }) };
  let following;
  let length = 0;
  const growingAnswer = () => [new AIMessage({ id: "growing", content: "answer ".repeat(++length) })];
  await act(async () => {
    following = create(React.createElement(AgentMessageFeed, { messages: growingAnswer() }), { createNodeMock: () => transcript });
  });
  assert.equal(scrolls.at(-1).behavior, "auto", "reduced motion disables animated following");
  const beforeSelection = scrolls.length;
  selected = true;
  await act(async () => following.update(React.createElement(AgentMessageFeed, { messages: growingAnswer() })));
  assert.equal(scrolls.length, beforeSelection, "new output must not move a selected passage");
  selected = false;
  transcript.scrollTop = 0;
  listeners.get("scroll")();
  await act(async () => following.update(React.createElement(AgentMessageFeed, { messages: growingAnswer() })));
  assert.equal(scrolls.length, beforeSelection, "reading older output must not jump to the bottom");
  transcript.scrollTop = 600;
  listeners.get("scroll")();
  reduced = false;
  await act(async () => following.update(React.createElement(AgentMessageFeed, { messages: growingAnswer() })));
  assert.equal(scrolls.at(-1).behavior, "smooth", "following resumes when the reader returns to the bottom");
  await act(async () => following.unmount());
  delete globalThis.HTMLElement;
  delete globalThis.window;
  delete globalThis.document;
} finally {
  await vite.close();
}

console.log("AgentMessageFeed semantic Markdown/rendering checks passed.");
