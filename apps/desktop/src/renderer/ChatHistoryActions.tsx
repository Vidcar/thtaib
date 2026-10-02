import { useState } from "react";

import "./ChatHistoryActions.css";
import { DeleteChatDialog } from "./DeleteChatDialog";
import { conversationTitle, formatWhen } from "./display";
import { errorMessage } from "./errors";
import { Icon } from "./Icon";
import type { ChatConversation } from "./types";

export interface ChatHistoryActionsProps {
  conversation: ChatConversation;
  onDeleted: (id: string) => void;
  onError: (message: string) => void;
}

const TRANSCRIPT_NOTE = "This file is a transcript. It is not a restore.";
const DOWNLOAD_LABEL = "Download a Markdown transcript. It is not a restore.";
const DELETE_LABEL = "Delete this chat. Project files and model files stay.";

export function ChatHistoryActions({ conversation, onDeleted, onError }: ChatHistoryActionsProps) {
  const [confirmDelete, setConfirmDelete] = useState(false);
  function download(): void {
    try {
      const root = document.querySelector(".transcript");
      downloadText(transcriptMarkdown(conversation, root), `${safeFilename(conversationTitle(conversation))}.md`, "text/markdown");
    } catch (error) {
      onError(errorMessage(error));
    }
  }
  return (
    <section className="chat-history-actions" aria-label="Conversation history actions">
      <button type="button" className="menu-action" title={DOWNLOAD_LABEL} onClick={download}>
        <Icon name="files" size={18} style={{ width: "18px", height: "18px" }} />
        <span>Download transcript<span className="sr-only">{DOWNLOAD_LABEL}</span></span>
      </button>
      <button type="button" className="menu-action" title={DELETE_LABEL} onClick={() => setConfirmDelete(true)}>
        <Icon name="close" size={18} style={{ width: "18px", height: "18px" }} />
        <span>Delete<span className="sr-only">{DELETE_LABEL}</span></span>
      </button>
      {confirmDelete ? <DeleteChatDialog conversation={conversation} onClose={() => setConfirmDelete(false)} onDeleted={onDeleted} /> : null}
    </section>
  );
}

function safeFilename(title: string): string {
  const cleaned = title.replace(/[^a-z0-9._-]+/gi, "-").replace(/^-+|-+$/g, "").slice(0, 80);
  return cleaned || "conversation";
}

function downloadText(text: string, filename: string, contentType: string): void {
  const blob = new Blob([text], { type: contentType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function transcriptMarkdown(conversation: ChatConversation, root: Element | null): string {
  const lines = [`# ${conversationTitle(conversation)}`, "", `Exported: ${formatWhen(new Date().toISOString())}`];
  const area = conversation.area_label || conversation.area_project_path;
  if (area) lines.push(`Area: ${area}`);
  lines.push("", TRANSCRIPT_NOTE, "");
  const retained: string[] = [];
  let sawMessage = false;
  if (root) {
    for (const child of Array.from(root.children)) sawMessage = walkTranscript(child, lines, retained) || sawMessage;
  }
  if (!sawMessage) lines.push("_No messages were saved in this conversation._", "");
  if (retained.length) {
    lines.push("", "## Retained files", "");
    for (const filename of retained) lines.push(`- ${filename}`);
    lines.push("");
  }
  return `${lines.join("\n").trimEnd()}\n`;
}

function walkTranscript(node: Element, lines: string[], retained: string[]): boolean {
  if (skipped(node)) return false;
  if (node.matches(".chat-retained-files")) {
    collectRetained(node, retained);
    return false;
  }
  if (node.matches(".helper-delegation")) {
    lines.push(helperLine(node));
    return false;
  }
  if (node.matches("ol") && node.getAttribute("aria-label") === "Todo list") {
    for (const item of Array.from(node.querySelectorAll("li"))) lines.push(todoLine(item));
    return false;
  }
  if (node.matches(".activity-line")) {
    const text = node.textContent?.trim() ?? "";
    if (text) lines.push(text);
    return false;
  }
  if (node.matches("summary")) {
    const line = node.querySelector(".activity-line");
    const text = line?.textContent?.trim() ?? "";
    if (text) lines.push(text);
    return false;
  }
  if (node.matches("article") && node.classList.contains("bubble-user")) {
    lines.push("## You", "", node.querySelector(".user-message-text")?.textContent ?? "", "");
    let saw = true;
    for (const child of Array.from(node.children)) saw = walkTranscript(child, lines, retained) || saw;
    return saw;
  }
  if (node.matches("article") && node.classList.contains("bubble-assistant")) {
    lines.push("## Assistant", "", node.getAttribute("data-markdown-source") ?? node.querySelector("[data-markdown-source]")?.getAttribute("data-markdown-source") ?? "", "");
    let saw = true;
    for (const child of Array.from(node.children)) saw = walkTranscript(child, lines, retained) || saw;
    return saw;
  }
  let saw = false;
  for (const child of Array.from(node.children)) saw = walkTranscript(child, lines, retained) || saw;
  return saw;
}

function skipped(node: Element): boolean {
  return node.matches(".message-reasoning, .tool-call-details, .tool-raw-arguments, .tool-call-error, .todo-arguments, .tool-call-permission, .message-attachments, .answer-actions, .message-task-actions, .activity-toggle, .tool-call-progress");
}

function helperLine(node: Element): string {
  const name = node.querySelector(".helper-delegation-head strong")?.textContent?.trim() ?? "";
  const status = node.querySelector(".helper-delegation-head span")?.textContent?.trim() ?? "";
  const request = node.querySelector(".helper-delegation-request")?.textContent?.trim() ?? "";
  return [name, status, request].filter(Boolean).join(" ");
}

function todoLine(item: Element): string {
  const mark = item.querySelector(".todo-status")?.textContent?.trim() ?? "";
  const rest: string[] = [];
  for (const child of Array.from(item.childNodes)) {
    if (child.nodeType === 1 && (child as Element).matches(".todo-status")) continue;
    rest.push(child.textContent ?? "");
  }
  return `${mark} ${rest.join("").trim()}`.trim();
}

function collectRetained(node: Element, retained: string[]): void {
  for (const name of Array.from(node.querySelectorAll(".retained-file-name span"))) {
    const filename = name.textContent?.trim() ?? "";
    if (filename && !retained.includes(filename)) retained.push(filename);
  }
}
