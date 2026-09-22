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
  const { sourceReference } = await vite.ssrLoadModule("/src/renderer/SourceReference.tsx");
  const sourceUrl = `workbench-source://asset_example/${"a".repeat(64)}?source=row+2&line=1&start=0&end=4`;
  assert.equal(sourceReference(sourceUrl).source, "row 2");
  for (const invalid of ["javascript:alert(1)", sourceUrl.replace("start=0", "start=-1"), sourceUrl.replace("asset_example", "../secret")]) assert.equal(sourceReference(invalid), null);
  const sourceHtml = renderToStaticMarkup(React.createElement(AgentMessageFeed, { sourceScope: { sessionId: "chat_example" }, messages: [new AIMessage({content: `The value is 42. [Source row](${sourceUrl})`})] }));
  assert.match(sourceHtml, /source-reference-link/, "answer source references open an internal source viewer");
  assert.doesNotMatch(sourceHtml, /href="workbench-source:/, "internal references must never navigate to a URI handler");
  const pixels = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a7ioAAAAASUVORK5CYII=";
  const screenshot = renderToStaticMarkup(React.createElement(AgentMessageFeed, { messages: [
    new AIMessage({ id: "screenshot-call", content: "", tool_calls: [{ id: "screen-1", name: "screenshot", args: {} }] }),
    new ToolMessage({ id: "screenshot-result", tool_call_id: "screen-1", content: [{ type: "image", source_type: "base64", mime_type: "image/png", data: pixels.split(",")[1] }] }),
  ] }));
  assert.match(screenshot, /aria-label="View image /, "screenshot outputs expose a clickable thumbnail even with details collapsed");
  assert.match(screenshot, /<img[^>]*src="data:image\/png;base64,/, "actual screenshot bytes render as an image");
  assert.doesNotMatch(screenshot, /<code>[^<]*iVBOR/, "image data must not appear as a wall of base64 output");
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
  assert.match(html, /<details class="message-reasoning"><summary aria-expanded="false">/);
  assert.ok(html.indexOf('class="message-reasoning"') < html.indexOf("Answer with"), "reasoning must precede its corresponding answer");
  assert.ok(html.includes("Provider supplied reasoning only."), "reasoning text should be preserved");
  assert.ok(!html.slice(0, html.indexOf('<details class="message-reasoning"')).includes("Provider supplied reasoning only."), "reasoning must not be mixed into answer markdown");
  assert.ok(html.includes("Image attachment: chart.png"), "image blocks should leave a visible attachment marker");
  assert.ok(html.includes("Tool result text"), "tool block results should render inside activity details");
  assert.ok(html.includes('data-state="completed">Done'), "tool block status should render honestly");
  assert.doesNotMatch(html, /Tool activity/, "actual tools must be named without a generic activity wrapper");
  assert.ok(html.includes('aria-label="Copy code block"'), "fenced code blocks should expose a copy button");
  assert.ok(!html.includes("<script>"), "raw HTML script tags must not render as elements");
  assert.ok(!html.includes('href="javascript:alert(1)"'), "unsafe javascript links must not render as links");

  const detailed = renderToStaticMarkup(React.createElement(AgentMessageFeed, { messages, detailedStreams: true }));
  assert.match(detailed, /<details class="message-reasoning" open=""><summary aria-expanded="true">/);
  assert.match(detailed, /<details class="message-tools" open=""><summary aria-expanded="true">/);

  const historical = renderToStaticMarkup(React.createElement(AgentMessageFeed, {messages: [
    new AIMessage({id: "saved-call", content: "", tool_calls: [{id: "call-old", name: "lookup", args: {q: "retained"}}]}),
    new ToolMessage({id: "saved-result", tool_call_id: "call-old", name: "lookup", content: "Saved lookup result"}),
  ]}));
  assert.ok(historical.includes("lookup") && historical.includes("retained"), "public contentBlocks must preserve hydrated tool calls without live tool events");
  assert.equal((historical.match(/class="message-tools"/g) ?? []).length, 1, "retained call and result must render one compact named activity");
  assert.match(historical, /class="tool-call-name"[^>]*>lookup<\/span>/, "tool name stays visible in the collapsed row");
  const historicalDetailsIndex = historical.indexOf('<details class="message-tools"');
  assert.ok(historicalDetailsIndex > -1, "compact tool result should be behind expandable details");
  assert.ok(!historical.slice(0, historicalDetailsIndex).includes("Saved lookup result"), "tool result text must not dump into the foreground when details are off");

  const errorTool = renderToStaticMarkup(React.createElement(AgentMessageFeed, {messages: [
    new ToolMessage({id: "saved-error", tool_call_id: "call-error", name: "write_file", content: "Error: write failed"}),
  ]}));
  assert.match(errorTool, /<p class="tool-call-error" role="status">Error: write failed<\/p>/, "tool errors should stay visible outside the collapsed details");

  const liveCall = { callId: "live-call", id: "live-call", name: "read_file", namespace: [], input: { file_path: "notes.txt" }, args: { file_path: "notes.txt" }, output: null, status: "running", error: undefined };
  const callingMessage = new AIMessage({ id: "calling", content: "Checking the file.", tool_calls: [{ id: liveCall.callId, name: liveCall.name, args: liveCall.input }] });
  const resultMessage = new ToolMessage({ id: "result", tool_call_id: liveCall.callId, content: "Saved file contents", status: "success" });
  const finalMessage = new AIMessage({ id: "final", content: "Final answer after file read." });
  const completedCall = { ...liveCall, status: "finished", output: "Actual SDK output" };
  const joined = renderToStaticMarkup(React.createElement(AgentMessageFeed, { messages: [callingMessage, resultMessage, finalMessage], toolCalls: [completedCall] }));
  assert.equal((joined.match(/class="message-tools"/g) ?? []).length, 1, "live call, retained call and unnamed result join by call identity");
  assert.match(joined, /class="tool-call-target"[^>]*>notes.txt<\/span>/, "tool target is visible before opening details");
  assert.match(joined, /Saved file contents/, "retained result is authoritative after hydration");
  assert.ok(joined.indexOf('class="message-tools"') < joined.indexOf("Final answer after file read"), "completed activity must stay before the final answer");

  const liveOnly = renderToStaticMarkup(React.createElement(AgentMessageFeed, { messages: [], toolCalls: [liveCall] }));
  assert.match(liveOnly, /read_file/, "tool activity must show even before any messages arrive");
  assert.match(liveOnly, /data-state="running">Running/, "active SDK status must be visible");
  const liveCompleted = renderToStaticMarkup(React.createElement(AgentMessageFeed, { messages: [callingMessage], toolCalls: [completedCall] }));
  assert.match(liveCompleted, /Actual SDK output/, "reactive SDK output field must be shown before result hydration");
  const literalOutput = "_before_ __literal__\n# not a heading\n<script>alert('x')</script><img src=x onerror=alert(1)>\n[unsafe](javascript:alert(1))\n```text\n  preserve_spaces_and_underscores  \n```\n";
  let literalRenderer;
  const originalNavigator = Object.getOwnPropertyDescriptor(globalThis, "navigator");
  const copies = [];
  Object.defineProperty(globalThis, "navigator", { configurable: true, value: { clipboard: { writeText: async value => { copies.push(value); } } } });
  try {
    await act(async () => { literalRenderer = create(React.createElement(AgentMessageFeed, { messages: [], toolCalls: [{ ...completedCall, output: literalOutput }], detailedStreams: true })); });
    const outputSection = literalRenderer.root.findByProps({ "aria-label": "Tool output" });
    assert.equal(outputSection.findByType("code").props.children, literalOutput, "tool output must preserve literal Markdown, HTML, whitespace and underscores");
    assert.equal(outputSection.findAll(node => ["a", "script", "img", "em", "strong", "h1"].includes(node.type)).length, 0, "tool output must not create markup or active HTML");
    await act(async () => { outputSection.findByProps({ "aria-label": "Copy code block" }).props.onClick(); await tick(); });
    assert.equal(copies.at(-1), literalOutput, "copy returns exact tool output bytes as text");
    const jsonOutput = { file_name: "_notes_.txt", count: 3, data: ["<b>literal</b>", true] };
    await act(async () => literalRenderer.update(React.createElement(AgentMessageFeed, { messages: [], toolCalls: [{ ...completedCall, output: jsonOutput }] })));
    assert.equal(literalRenderer.root.findByProps({ "aria-label": "Tool output" }).findByType("code").props.children, JSON.stringify(jsonOutput, null, 2), "structured output uses readable raw JSON");
  } finally {
    if (literalRenderer) await act(async () => literalRenderer.unmount());
    if (originalNavigator) Object.defineProperty(globalThis, "navigator", originalNavigator);
    else delete globalThis.navigator;
  }
  const rawHtml = renderToStaticMarkup(React.createElement(AgentMessageFeed, { messages: [], toolCalls: [{ ...completedCall, output: literalOutput }] }));
  assert.ok(rawHtml.includes("&lt;script&gt;"));
  assert.doesNotMatch(rawHtml, /<script>|<img|href="javascript:/);
  const liveError = renderToStaticMarkup(React.createElement(AgentMessageFeed, { messages: [], toolCalls: [{ ...liveCall, status: "error", error: "Access denied by the tool" }] }));
  assert.match(liveError, /<p class="tool-call-error" role="status">Access denied by the tool<\/p>/, "SDK errors must be visible without opening details");
  const successDiscussingErrors = renderToStaticMarkup(React.createElement(AgentMessageFeed, { messages: [new ToolMessage({ id: "logs", name: "grep", tool_call_id: "logs-call", status: "success", content: "Error count: 0. No failed checks." })] }));
  assert.doesNotMatch(successDiscussingErrors, /tool-call-failed|tool-call-error/, "successful output mentioning errors is not a failed tool");
  const concurrentCalls = renderToStaticMarkup(React.createElement(AgentMessageFeed, { messages: [], toolCalls: [liveCall, { ...liveCall, id: "second-call", callId: "second-call", input: { file_path: "other.txt" } }] }));
  assert.equal((concurrentCalls.match(/class="message-tools"/g) ?? []).length, 2, "distinct calls to the same tool keep separate identities");
  assert.match(concurrentCalls, /other.txt/, "distinct call input must stay paired with its own row");
  const serverTool = renderToStaticMarkup(React.createElement(AgentMessageFeed, { messages: [{ id: "server-blocks", getType: () => "ai", content: [
    { type: "server_tool_call", id: "server-call", name: "search", args: { query: "model docs" } },
    { type: "server_tool_call_result", id: "output-block", toolCallId: "server-call", status: "success", output: "Matching documentation" },
  ] }] }));
  assert.equal((serverTool.match(/class="message-tools"/g) ?? []).length, 1, "server tool call and output blocks also join by their call identity");
  assert.match(serverTool, /Matching documentation/, "joined server tool result is retained");

  let toolRenderer;
  await act(async () => { toolRenderer = create(React.createElement(AgentMessageFeed, { messages: [], toolCalls: [liveCall] })); });
  await toggleDetails(toolRenderer.root, "message-tools", true);
  await act(async () => { toolRenderer.update(React.createElement(AgentMessageFeed, { messages: [callingMessage, resultMessage, finalMessage], toolCalls: [completedCall] })); });
  assert.equal(toolRenderer.root.findAllByType("details").length, 1, "hydration must not duplicate a live tool row");
  assert.equal(detailsOpen(toolRenderer.root, "message-tools"), true, "expanded live tool remains open when attached to its retained call");
  await toggleDetails(toolRenderer.root, "message-tools", false);
  await act(async () => { toolRenderer.update(React.createElement(AgentMessageFeed, { messages: [callingMessage, resultMessage, finalMessage], detailedStreams: true })); });
  assert.equal(detailsOpen(toolRenderer.root, "message-tools"), false, "explicit tool collapse survives completion, hydration and detailed-stream preference changes");
  await act(async () => toolRenderer.unmount());

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
  let initiallyEmpty;
  await act(async () => { initiallyEmpty = create(React.createElement(AgentMessageFeed, { messages: [] }), { createNodeMock: () => transcript }); });
  await act(async () => initiallyEmpty.update(React.createElement(AgentMessageFeed, { messages: growingAnswer() })));
  assert.ok(listeners.has("scroll"), "a feed mounted empty must start tracking the reader when its first message arrives");
  await act(async () => initiallyEmpty.unmount());
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
  await act(async () => following.update(React.createElement(AgentMessageFeed, { messages: [], toolCalls: [liveCall] })));
  const beforeToolCompletion = scrolls.length;
  await act(async () => following.update(React.createElement(AgentMessageFeed, { messages: [], toolCalls: [completedCall] })));
  assert.ok(scrolls.length > beforeToolCompletion, "following also responds to tool output when no answer text changes");
  await act(async () => following.unmount());
  delete globalThis.HTMLElement;
  delete globalThis.window;
  delete globalThis.document;
} finally {
  await vite.close();
}

console.log("AgentMessageFeed semantic Markdown/rendering checks passed.");
