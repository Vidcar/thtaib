import React from "react";
import { createRoot } from "react-dom/client";
import { AIMessage, HumanMessage } from "@langchain/core/messages";
import { AgentMessageFeed } from "../../src/renderer/AgentMessageFeed";
import "../../src/renderer/appearanceDefaults.css";
import "../../src/renderer/styles.css";
import "../../src/renderer/ChatPanel.css";
const root = createRoot(document.getElementById("root")!);
let messages: Array<AIMessage | HumanMessage> = [];
const retainedAnswers = new Set<string>();
const paint = (live = false) => root.render(<div className="chat-main" style={{ width: 900 }}><div className="transcript" tabIndex={0} style={{ height: 600, flex: "none" }}><AgentMessageFeed messages={messages} live={live} renderAnswerActions={message => message.id && retainedAnswers.has(message.id) ? <div className="answer-actions"><button className="icon-button" aria-label="Copy answer">Copy</button></div> : null} /></div></div>);
const frame = () => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
const geometry = () => { const transcript = document.querySelector(".transcript")!; return { top: transcript.scrollTop, height: transcript.scrollHeight, client: transcript.clientHeight, jump: Boolean(document.querySelector('[aria-label="Jump to latest message"]')) }; };
Object.assign(window, { fixture: {
  frame, geometry,
  async turn(count = 40) {
    const prefix = messages; const id = `turn_${messages.length}`;
    messages = [...prefix, new HumanMessage({ id: `human_${id}`, content: "Continue with the next numbered lines." })]; paint(true); await frame();
    const samples = [];
    for (let i=1; i<=count; i++) {
      messages = [...prefix, new HumanMessage({ id: `human_${id}`, content: "Continue with the next numbered lines." }), new AIMessage({ id, content: Array.from({ length:i }, (_, n) => `${n + 1}. Row ${n + 1}: Trees transport water and support living ecosystems.`).join("\n") })];
      paint(true); await frame(); samples.push(geometry());
    }
    paint(false); await frame(); samples.push(geometry());
    // The durable saved answer arrives after streaming finishes, enabling its
    // action row without changing the message text or completion signature.
    retainedAnswers.add(id); paint(false); await frame(); samples.push(geometry()); return samples;
  },
  async grow() { const last=messages.at(-1)!; messages=[...messages.slice(0,-1),new AIMessage({id:last.id,content:String(last.content)+"\n41. Another new line."})]; paint(true); await frame(); return geometry(); },
} });
paint();
