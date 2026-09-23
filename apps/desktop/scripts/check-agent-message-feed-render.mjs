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
  const summary = details.findAllByType("summary")[0];
  return summary.props["aria-expanded"] === true;
}

async function toggleDetails(root, className, open) {
  const details = findByClass(root, className);
  assert.ok(details, `${className} details should render`);
  assert.notEqual(detailsOpen(root, className), open, `${className} details should start in the opposite state before this toggle`);
  const summary = details.findAllByType("summary")[0];
  await act(async () => {
    summary.props.onClick({ preventDefault() {} });
    await tick();
  });
}

function tick() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

try {
  const feedModule = await vite.ssrLoadModule("/src/renderer/AgentMessageFeed.tsx");
  const { AgentMessageFeed, resetPaintCounters } = feedModule;
  const { splitStreamingMarkdown } = await vite.ssrLoadModule("/src/renderer/streamingMarkdown.ts");
  const answerBody = (text, live) => renderToStaticMarkup(React.createElement(AgentMessageFeed, {
    messages: [new AIMessage({ id: "semantic-answer", content: text })],
    incompleteMessageIds: new Set(live ? ["semantic-answer"] : []),
  })).match(/<div class="message-body">([\s\S]*?)<\/div><\/article>/)?.[1].replace(/>\n</g, "><");
  for (const text of [
    "1. First item.\n\n   Another paragraph in the first item.\n\n2. Second item.\n",
    "Read [the manual][guide].\n\n[guide]: https://example.com/manual\n\nMore text.",
    "> First quote paragraph.\n>\n> Second quote paragraph.\n\nAfter the quote.",
    "```text\nA literal ** marker\n```\n\nAfter code.",
  ]) {
    assert.equal(answerBody(text, true), answerBody(text, false), "streaming must preserve the settled Markdown meaning, including document and container context");
  }
  const manyThoughts = Array.from({ length: 30 }, (_, index) => `Thought ${index}: ${"long reasoning paragraph ".repeat(index + 1)}`).join("\n\n");
  const longReasoning = renderToStaticMarkup(React.createElement(AgentMessageFeed, {
    messages: [new AIMessage({ id: "long-reasoning", content: [{ type: "reasoning", reasoning: manyThoughts }] })], detailedStreams: true,
  }));
  assert.match(longReasoning, /Thought 0:/, "opening a long reasoning body keeps its beginning reachable in the same scroll container");
  assert.match(longReasoning, /Thought 29:/, "opening a long reasoning body keeps its final paragraph");
  const fenced = splitStreamingMarkdown("Done paragraph.\n\n```ts\nconst value = 1;\n");
  assert.deepEqual(fenced.blocks, ["Done paragraph."]);
  assert.match(fenced.tail, /```ts/);
  assert.doesNotMatch(fenced.tail, /Done paragraph/);
  const continued = splitStreamingMarkdown("Done paragraph.\n\nStill writing");
  assert.deepEqual(continued.blocks, ["Done paragraph."]);
  assert.equal(continued.tail, "Still writing");
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
  assert.doesNotMatch(html, /bubble-settled/, "the live answer stays active while it is still streaming");
  assert.match(html, /<details class="message-reasoning"><summary aria-expanded="false">/);
  assert.ok(html.indexOf('class="message-reasoning"') < html.indexOf("Answer with"), "reasoning must precede its corresponding answer");
  assert.ok(html.includes("Provider supplied reasoning only."), "reasoning text should be preserved");
  assert.ok(!html.slice(0, html.indexOf('<details class="message-reasoning"')).includes("Provider supplied reasoning only."), "reasoning must not be mixed into answer markdown");
  assert.ok(html.includes("Image attachment: chart.png"), "image blocks should leave a visible attachment marker");
  assert.ok(html.includes("Tool result text"), "tool block results should render inside activity details");
  assert.match(html, /Called search/, "a finished call leads with what happened");
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
  assert.match(historical, /Saved lookup result/, "a finished answer retains its readable saved result");
  assert.ok(historical.includes("lookup") && historical.includes("retained"), "public contentBlocks must preserve hydrated tool calls without live tool events");
  assert.equal((historical.match(/class="message-tools"/g) ?? []).length, 1, "retained call and result must render one compact named activity");
  assert.match(historical, /Called lookup/, "a finished call leads with the action");
  assert.match(historical, /class="tool-call-name"[^>]*>lookup<\/span>/, "the tool name stays available on expand");
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
  assert.match(joined, /Read notes.txt/, "a finished read names the file without a diff count");
  assert.match(joined, /Saved file contents/, "retained result is authoritative after hydration");
  assert.ok(joined.indexOf('class="message-tools"') < joined.indexOf("Final answer after file read"), "completed activity must stay before the final answer");

  const liveOnly = renderToStaticMarkup(React.createElement(AgentMessageFeed, { messages: [], toolCalls: [liveCall] }));
  assert.match(liveOnly, /Reading notes.txt/, "tool activity must show even before any messages arrive");
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
  const fileStart = ".bench-1 { color: #111; }";
  const fileEnd = ".bench-160 { color: #eee; }";
  const fileBody = `${fileStart}\n${Array.from({ length: 400 }, (_, index) => `rule ${index}`).join("\n")}\n${fileEnd}`;
  const rawWrite = JSON.stringify({ file_path: "stream-bench.html", content: fileBody });
  const preparingCall = { callId: "write-live", id: "write-live", name: "write_file", namespace: [], input: rawWrite, args: rawWrite, output: null, status: "preparing", error: undefined };
  const preparingClosed = renderToStaticMarkup(React.createElement(AgentMessageFeed, { messages: [], toolCalls: [preparingCall] }));
  assert.match(preparingClosed, /stream-bench\.html/, "a live write names the file on the row");
  assert.match(preparingClosed, /KB proposed/, "streamed input describes proposed bytes until the tool succeeds");
  const awaitingApproval = renderToStaticMarkup(React.createElement(AgentMessageFeed, { messages: [new AIMessage({ id: "needs-approval", content: "", tool_calls: [{ id: preparingCall.callId, name: "write_file", args: { file_path: "stream-bench.html", content: fileBody } }] })], toolCalls: [preparingCall], live: true, waiting: true, detailedStreams: true }));
  assert.match(awaitingApproval, /Waiting for your response/);
  assert.match(awaitingApproval, /Proposed change to stream-bench.html/);
  assert.doesNotMatch(awaitingApproval, /characters written|KB written|>Writing<|Created stream-bench|Creating stream-bench/, "awaiting authorization cannot claim an executing or completed write");
  assert.doesNotMatch(preparingClosed, /rule 10|bench-160/, "a collapsed live write does not paint the file");
  const preparingOpen = renderToStaticMarkup(React.createElement(AgentMessageFeed, { messages: [], toolCalls: [preparingCall], detailedStreams: true }));
  assert.doesNotMatch(preparingOpen, /Showing the latest 4,000 characters/);
  assert.match(preparingOpen, /bench-160 \{ color: #eee; \}/, "the open live write shows the newest lines");
  assert.match(preparingOpen, /\.bench-1 \{ color: #111; \}/, "the native scroll body retains its entire text without estimating each line height");
  assert.doesNotMatch(preparingOpen, /\\n\.bench-160/, "escaped newlines in a streamed file are shown as line breaks");
  let finishedInput;
  await act(async () => { finishedInput = create(React.createElement(AgentMessageFeed, { messages: [], toolCalls: [preparingCall], live: true, detailedStreams: true })); });
  const retainedInputScroller = finishedInput.root.findByProps({ className: "tool-input-text" });
  const completeWrite = { ...preparingCall, input: { file_path: "stream-bench.html", content: fileBody }, args: { file_path: "stream-bench.html", content: fileBody }, status: "finished", output: "Created stream-bench.html" };
  await act(async () => finishedInput.update(React.createElement(AgentMessageFeed, { messages: [], toolCalls: [completeWrite], live: false, detailedStreams: true })));
  assert.equal(finishedInput.root.findByProps({ "aria-label": "Tool input" }).findAllByType("code")[0].props.children, fileBody, "a completed file write keeps readable full file content rather than escaped JSON");
  assert.equal(finishedInput.root.findByProps({ className: "tool-input-text" }), retainedInputScroller, "the same native scroll body survives file-write completion");
  const rawArguments = finishedInput.root.findByProps({ className: "tool-raw-arguments" });
  assert.notEqual(rawArguments.props.open, true, "raw arguments stay behind a collapsed disclosure");
  assert.equal(rawArguments.findByType("code").props.children, JSON.stringify(completeWrite.input, null, 2), "raw tool arguments remain available without altering file contents");
  await act(async () => finishedInput.unmount());
  let stoppedInput;
  await act(async () => { stoppedInput = create(React.createElement(AgentMessageFeed, { messages: [], toolCalls: [preparingCall], live: true, detailedStreams: true })); });
  await act(async () => stoppedInput.update(React.createElement(AgentMessageFeed, { messages: [], toolCalls: [preparingCall], live: false, detailedStreams: true })));
  const stoppedTree = JSON.stringify(stoppedInput.toJSON());
  assert.match(stoppedTree, /Partial input/, "terminal runs retain unfinished tool input as partial output");
  assert.match(stoppedTree, /Unfinished input for stream-bench.html/, "unfinished tool preparation must not claim the file was created");
  assert.doesNotMatch(stoppedTree, /Creating stream-bench|Created stream-bench|Writing|characters written|KB written/, "a terminal tool cannot still claim active writing or successful execution");
  assert.equal(stoppedInput.root.findByProps({ "aria-label": "Tool input" }).findByType("code").props.children, fileBody, "terminal presentation preserves the entire readable input");
  await act(async () => stoppedInput.update(React.createElement(AgentMessageFeed, { messages: [new HumanMessage({ id: "new-after-stop", content: "A new request" })], toolCalls: [preparingCall], live: true, detailedStreams: true })));
  assert.match(JSON.stringify(stoppedInput.toJSON()), /Partial input/, "a new turn cannot reactivate an unfinished tool from the previous turn");
  await act(async () => stoppedInput.unmount());
  const hydratedPartial = new AIMessage({ id: "hydrated-partial-tool", content: [
    { type: "reasoning", reasoning: "The generation ended while preparing file input." },
    { type: "tool_call_chunk", id: "partial-write", name: "write_file", args: rawWrite.slice(0, -2) },
  ] });
  assert.deepEqual(hydratedPartial.tool_calls, [], "retained unfinished arguments are inert display content, never executable tool calls");
  let reopenedPartial;
  await act(async () => { reopenedPartial = create(React.createElement(AgentMessageFeed, { messages: [hydratedPartial], incompleteMessageIds: new Set([hydratedPartial.id]), live: false, detailedStreams: true })); });
  assert.match(JSON.stringify(reopenedPartial.toJSON()), /Unfinished input for stream-bench.html/, "a reopened failed run renders its saved unfinished tool input without replaying token events");
  assert.equal(reopenedPartial.root.findByProps({ "aria-label": "Tool input" }).findByType("code").props.children, fileBody, "inert snapshot tool content preserves the entire readable partial input");
  assert.doesNotMatch(JSON.stringify(reopenedPartial.toJSON()), /Creating stream-bench|Created stream-bench|Writing|KB written/);
  const liveHydratedPartial = renderToStaticMarkup(React.createElement(AgentMessageFeed, { messages: [hydratedPartial], incompleteMessageIds: new Set([hydratedPartial.id]), live: true, detailedStreams: true }));
  assert.match(liveHydratedPartial, /Creating stream-bench.html/, "hydrating an unfinished tool during an active run retains its live presentation");
  await act(async () => reopenedPartial.unmount());
  const escapedWrite = renderToStaticMarkup(React.createElement(AgentMessageFeed, { messages: [], toolCalls: [{ ...preparingCall, input: '{"file_path":"unicode.txt","content":"\\u0041\\uD83D\\uDE03\\n' }], detailedStreams: true }));
  assert.match(escapedWrite, /A😃/, "partial JSON strings preserve escaped Unicode and surrogate pairs in the live tool preview");
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
  assert.equal(toolRenderer.root.findAll(node => node.type === "details" && node.props.className === "message-tools").length, 1, "hydration must not duplicate a live tool row");
  assert.equal(detailsOpen(toolRenderer.root, "message-tools"), true, "expanded live tool remains open when attached to its retained call");
  await toggleDetails(toolRenderer.root, "message-tools", false);
  await act(async () => { toolRenderer.update(React.createElement(AgentMessageFeed, { messages: [callingMessage, resultMessage, finalMessage], detailedStreams: true })); });
  assert.equal(detailsOpen(toolRenderer.root, "message-tools"), false, "explicit tool collapse survives completion, hydration and detailed-stream preference changes");
  await act(async () => toolRenderer.unmount());

  let changedOutput;
  await act(async () => { changedOutput = create(React.createElement(AgentMessageFeed, { messages: [callingMessage], toolCalls: [{ ...completedCall, output: "Alpha" }], detailedStreams: true })); });
  await act(async () => changedOutput.update(React.createElement(AgentMessageFeed, { messages: [callingMessage], toolCalls: [{ ...completedCall, output: "Omega" }], detailedStreams: true })));
  assert.equal(changedOutput.root.findByProps({ "aria-label": "Tool output" }).findByType("code").props.children, "Omega", "a revised result with the same length must replace the old displayed result");
  await act(async () => changedOutput.unmount());

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

  const settled = new AIMessage({ id: "settled", content: "Finished paragraph.\n\nStill here." });
  const waitingTurn = renderToStaticMarkup(React.createElement(AgentMessageFeed, { messages: [settled, new HumanMessage({ id: "latest-human", content: "Another question" })], live: true }));
  assert.doesNotMatch(waitingTurn, /Response in progress|Incomplete response/, "waiting for a new answer must not mark a previous answer as writing");
  const nextTurn = renderToStaticMarkup(React.createElement(AgentMessageFeed, { messages: [settled, new HumanMessage({ id: "latest-human", content: "Another question" }), new AIMessage({ id: "next-answer", content: "New answer" })], live: true }));
  assert.equal((nextTurn.match(/Response in progress/g) ?? []).length, 1, "only the latest answer after the most recent user turn is writing");
  const continuation = renderToStaticMarkup(React.createElement(AgentMessageFeed, { messages: [callingMessage, resultMessage, finalMessage] }));
  assert.equal((continuation.match(/bubble-continuation/g) ?? []).length, 1, "tool-separated assistant continuations share one assistant role heading");
  const growingLive = (extra) => new AIMessage({ id: "live-answer", content: `Partial ${extra}` });
  let bubbleRenderer;
  await act(async () => { bubbleRenderer = create(React.createElement(AgentMessageFeed, { messages: [settled, growingLive("one")], incompleteMessageIds: new Set(["live-answer"]) })); });
  resetPaintCounters();
  const parsesBefore = feedModule.markdownParseCount;
  await act(async () => { bubbleRenderer.update(React.createElement(AgentMessageFeed, { messages: [settled, growingLive("two")], incompleteMessageIds: new Set(["live-answer"]) })); });
  assert.equal(feedModule.finishedBubbleRenders, 0, "a parent render that does not change finished text does not rebuild that bubble");
  assert.equal(feedModule.markdownParseCount - parsesBefore, 1, "growing the open tail parses only the updated live paragraph");
  await act(async () => bubbleRenderer.unmount());

  let writeRenderer;
  const toolListeners = new Map();
  const toolScroll = {
    top: 0, scrollHeight: 8000, clientHeight: 400,
    get scrollTop() { return this.top; },
    set scrollTop(value) { this.top = Math.min(value, this.scrollHeight - this.clientHeight); },
    addEventListener(name, handler) { toolListeners.set(name, handler); },
    removeEventListener(name) { toolListeners.delete(name); },
    contains() { return false; },
  };
  await act(async () => { writeRenderer = create(React.createElement(AgentMessageFeed, { messages: [], toolCalls: [preparingCall], detailedStreams: true }), { createNodeMock: element => element.props.className === "tool-input-text" ? toolScroll : null }); });
  const scroller = writeRenderer.root.findByProps({ className: "tool-input-text" });
  assert.equal(scroller.findByType("code").props.children, fileBody, "the native scroll body retains the exact complete tool input");
  assert.equal(toolScroll.scrollTop, 7600, "a live tool preview starts at its newest line using measured browser geometry");
  toolScroll.scrollTop = 0;
  toolListeners.get("scroll")();
  await act(async () => writeRenderer.update(React.createElement(AgentMessageFeed, { messages: [], toolCalls: [{ ...preparingCall, input: JSON.stringify({ file_path: "stream-bench.html", content: `${fileBody}\nMore content` }) }], detailedStreams: true })));
  assert.equal(toolScroll.scrollTop, 0, "reading earlier tool input is preserved when more content arrives");
  const writeNavigator = Object.getOwnPropertyDescriptor(globalThis, "navigator");
  const writeCopies = [];
  Object.defineProperty(globalThis, "navigator", { configurable: true, value: { clipboard: { writeText: async value => { writeCopies.push(value); } } } });
  try {
    await act(async () => { writeRenderer.root.findByProps({ "aria-label": "Copy tool input" }).props.onClick(); await tick(); });
    assert.match(writeCopies.at(-1), /bench-1/);
    assert.match(writeCopies.at(-1), /bench-160/);
  } finally {
    if (writeNavigator) Object.defineProperty(globalThis, "navigator", writeNavigator);
    else delete globalThis.navigator;
  }
  await act(async () => writeRenderer.unmount());

  const frameCallbacks = new Map();
  let frameRequests = 0;
  const oldWindow = globalThis.window;
  globalThis.window = {
    requestAnimationFrame: callback => { frameCallbacks.set(++frameRequests, callback); return frameRequests; },
    cancelAnimationFrame: id => frameCallbacks.delete(id),
  };
  let paced;
  const pacedProps = text => ({ messages: [new AIMessage({ id: "paced", content: text })], incompleteMessageIds: new Set(["paced"]) });
  try {
    await act(async () => { paced = create(React.createElement(AgentMessageFeed, pacedProps("first"))); });
    await act(async () => paced.update(React.createElement(AgentMessageFeed, pacedProps("first second"))));
    await act(async () => paced.update(React.createElement(AgentMessageFeed, pacedProps("first second third"))));
    assert.equal(frameRequests, 1, "arrivals before a paint share the original pending frame instead of postponing it");
    await act(async () => frameCallbacks.values().next().value());
    assert.match(JSON.stringify(paced.toJSON()), /first second third/, "the scheduled paint publishes every token received so far");
    await act(async () => paced.update(React.createElement(AgentMessageFeed, { messages: [new AIMessage({ id: "paced", content: "Final complete answer" })] })));
    assert.match(JSON.stringify(paced.toJSON()), /Final complete answer/, "completion flushes immediately even before another animation frame");
  } finally {
    if (paced) await act(async () => paced.unmount());
    if (oldWindow === undefined) delete globalThis.window;
    else globalThis.window = oldWindow;
  }

  const scrolls = [];
  const listeners = new Map();
  const resizeCallbacks = new Set();
  const originalResizeObserver = globalThis.ResizeObserver;
  globalThis.ResizeObserver = class {
    constructor(callback) { this.callback = callback; resizeCallbacks.add(callback); }
    observe() { resizeCallbacks.add(this.callback); }
    disconnect() { resizeCallbacks.delete(this.callback); }
  };
  class Transcript {
    scrollHeight = 1000;
    scrollTop = 600;
    clientHeight = 400;
    closest() { return this; }
    contains(node) { return node === this; }
    addEventListener(name, handler) { listeners.set(name, handler); }
    removeEventListener(name) { listeners.delete(name); }
    scrollTo(options) { scrolls.push(options); this.scrollTop = Math.max(0, this.scrollHeight - this.clientHeight); }
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
  transcript.scrollTop = 0;
  await act(async () => { initiallyEmpty = create(React.createElement(AgentMessageFeed, { messages: [] }), { createNodeMock: () => transcript }); });
  await act(async () => initiallyEmpty.update(React.createElement(AgentMessageFeed, { messages: growingAnswer() })));
  assert.ok(listeners.has("scroll"), "a feed mounted empty must start tracking the reader when its first message arrives");
  assert.equal(transcript.scrollTop, 600, "opening a saved conversation starts at its latest message even before a scroll position exists");
  await act(async () => initiallyEmpty.unmount());
  await act(async () => {
    following = create(React.createElement(AgentMessageFeed, { messages: growingAnswer() }), { createNodeMock: () => transcript });
  });
  assert.equal(scrolls.at(-1).behavior, "auto", "reduced motion disables animated following");
  transcript.scrollHeight = 1400;
  await act(async () => { for (const resize of resizeCallbacks) resize(); });
  assert.equal(transcript.scrollTop, 1000, "late layout growth follows the end without waiting for another token");
  transcript.scrollHeight = 1000;
  transcript.scrollTop = 600;
  await act(async () => { for (const resize of resizeCallbacks) resize(); });
  const beforeSelection = scrolls.length;
  selected = true;
  await act(async () => following.update(React.createElement(AgentMessageFeed, { messages: growingAnswer() })));
  assert.equal(scrolls.length, beforeSelection, "new output must not move a selected passage");
  selected = false;
  transcript.scrollTop = 0;
  await act(async () => listeners.get("scroll")());
  await act(async () => following.update(React.createElement(AgentMessageFeed, { messages: growingAnswer() })));
  assert.equal(scrolls.length, beforeSelection, "reading older output must not jump to the bottom");
  const jumpButton = following.root.findByProps({ "aria-label": "Jump to latest message" });
  selected = true;
  await act(async () => jumpButton.props.onClick());
  assert.equal(transcript.scrollTop, 600, "an explicit jump returns to the newest response even while old text remains selected");
  selected = false;
  transcript.scrollTop = 600;
  await act(async () => listeners.get("scroll")());
  reduced = false;
  await act(async () => following.update(React.createElement(AgentMessageFeed, { messages: growingAnswer() })));
  assert.equal(scrolls.at(-1).behavior, "auto", "following resumes at the newest line without a smooth chase");
  await act(async () => following.update(React.createElement(AgentMessageFeed, { messages: [], toolCalls: [liveCall] })));
  const beforeToolInput = scrolls.length;
  await act(async () => following.update(React.createElement(AgentMessageFeed, { messages: [], toolCalls: [{ ...liveCall, input: { file_path: "new-longer-path.txt" } }] })));
  assert.ok(scrolls.length > beforeToolInput, "following reacts to growing tool input before any output arrives");
  const beforeToolCompletion = scrolls.length;
  await act(async () => following.update(React.createElement(AgentMessageFeed, { messages: [], toolCalls: [completedCall] })));
  assert.ok(scrolls.length > beforeToolCompletion, "following also responds to tool output when no answer text changes");
  await act(async () => following.unmount());
  delete globalThis.HTMLElement;
  delete globalThis.window;
  delete globalThis.document;
  if (originalResizeObserver === undefined) delete globalThis.ResizeObserver;
  else globalThis.ResizeObserver = originalResizeObserver;
} finally {
  await vite.close();
}

console.log("AgentMessageFeed semantic Markdown/rendering checks passed.");
