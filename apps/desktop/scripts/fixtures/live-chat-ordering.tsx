import React from "react";
import { createRoot } from "react-dom/client";
import { ChatPanel } from "../../src/renderer/ChatPanel";
import "../../src/renderer/appearanceDefaults.css";
import "../../src/renderer/styles.css";
import "../../src/renderer/ChatPanel.css";

const backend = new URL(location.href).searchParams.get("backend")!;
Object.assign(window, { workbench: { backendUrl: backend } });
const root = createRoot(document.getElementById("root")!);
root.render(<div style={{ height: "100vh", width: "100%", maxWidth: 1000, minHeight: 0 }}><ChatPanel chatLaunch={{ id: "ordering-launch", kind: "open", conversationId: "conv_a" }} /></div>);
const frame = () => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
const feed = () => document.querySelector(".message-feed");
const transcript = () => document.querySelector(".transcript") as HTMLElement;
const bubbleNodes = () => [...(feed()?.querySelectorAll("article") ?? [])];
const toolNodes = () => [...(feed()?.querySelectorAll("details.message-tools") ?? [])];
const labels = () => bubbleNodes().map(node => node.textContent!.match(/TURN (?:ONE|TWO|THREE)|CHECK \d|FINAL \d|turn-\d\.txt/)?.[0] ?? "UNKNOWN");
const readableText = () => { const copy = feed()?.cloneNode(true) as HTMLElement | undefined; copy?.querySelectorAll(".activity-toggle").forEach(node => node.remove()); return copy?.textContent ?? ""; };
const geometry = () => { const el = transcript(); return { top: el.scrollTop, height: el.scrollHeight, client: el.clientHeight, jump: Boolean(document.querySelector('[aria-label="Jump to latest message"]')) }; };
const usage = () => {
  const bubble = document.querySelector(".chat-usage-bubble") as HTMLElement | null;
  const trigger = document.querySelector(".chat-usage-trigger") as HTMLElement | null;
  const rect = (node: Element | null) => node?.getBoundingClientRect().toJSON();
  const triggerText = trigger?.querySelector("span");
  const triggerRange = document.createRange();
  if (triggerText) triggerRange.selectNodeContents(triggerText);
  return {
    trigger: trigger?.textContent, triggerRect: rect(trigger), triggerTextRect: triggerText ? triggerRange.getBoundingClientRect().toJSON() : null,
    stopRect: rect(document.querySelector(".compose .stop-button")), focused: document.activeElement === trigger,
    liveStatusCount: document.querySelectorAll(".compose .chat-measurements").length,
    transcriptStates: [...(feed()?.querySelectorAll(".message-state") ?? [])].map(node => node.textContent),
    tooltip: bubble ? {
      rect: rect(bubble), text: bubble.textContent, background: getComputedStyle(bubble).backgroundColor,
      horizontalOverflow: bubble.scrollWidth - bubble.clientWidth,
      context: bubble.querySelector(".usage-context-value")?.textContent,
      rows: [...bubble.querySelectorAll(".usage-token-counts > div")].map(row => {
        const term = row.querySelector("dt")!, value = row.querySelector("dd")!;
        const range = document.createRange(); range.selectNodeContents(value);
        return { label: term.textContent, value: value.textContent, labelRect: rect(term), valueRect: rect(value), lines: range.getClientRects().length };
      }),
    } : null,
  };
};
let firstFeed: Element | null, firstBubble: Element, firstTool: Element;
Object.assign(window, { fixture: {
  frame, labels, geometry, usage, lastAnswer: () => bubbleNodes().at(-1)?.textContent ?? "",
  async appearance(theme: "dark" | "light", larger: boolean) {
    document.documentElement.dataset.theme = theme;
    for (const [name, value] of Object.entries({ "--text-small": "15px", "--text-body": "18px", "--text-ui": "19px" })) {
      if (larger) document.documentElement.style.setProperty(name, value);
      else document.documentElement.style.removeProperty(name);
    }
    await frame();
  },
  async serverState() { return (await fetch(`${backend}/fixture/action`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ action: "state" }) })).json(); },
  async action(action: string, number?: number, line?: number) { const res = await fetch(`${backend}/fixture/action`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ action, number, line }) }); if (!res.ok) throw new Error(await res.text()); await frame(); return this.snapshot(); },
  snapshot() { const old = bubbleNodes()[0] as HTMLElement; return { labels: labels(), tools: toolNodes().length, text: feed()?.textContent ?? "", readableText: readableText(), geometry: geometry(), feedSame: !firstFeed || feed() === firstFeed, bubbleSame: !firstBubble || bubbleNodes()[2] === firstBubble, toolSame: !firstTool || toolNodes()[0] === firstTool, disclosureOpen: (toolNodes()[0]?.querySelector("summary") as HTMLElement)?.getAttribute("aria-expanded") === "true", selection: getSelection()?.toString() ?? "", layout: { old: old?.getBoundingClientRect().toJSON(), transcript: transcript()?.getBoundingClientRect().toJSON(), visibility: old && getComputedStyle(old).visibility } }; },
  async remember() { firstFeed = feed(); firstBubble = bubbleNodes()[2]; firstTool = toolNodes()[0]; (firstTool.querySelector("summary") as HTMLElement).click(); await frame(); return this.snapshot(); },
  async selectOld() { const node = bubbleNodes()[0].querySelector(".user-message-text")!; node.scrollIntoView({ block: "center" }); await frame(); const range = document.createRange(); range.selectNodeContents(node); const selection = getSelection()!; selection.removeAllRanges(); selection.addRange(range); return selection.toString(); },
  clearSelection() { getSelection()?.removeAllRanges(); },
} });
