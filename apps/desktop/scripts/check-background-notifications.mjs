import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";
import ts from "typescript";

const require = createRequire(import.meta.url);
const source = ts.transpileModule(readFileSync(new URL("../src/main/background.ts", import.meta.url), "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true },
}).outputText;

const success = item("success", null, "agent_completed");
const approval = item("approval", "chat_waiting", "agent_waiting");
const question = item("question", null, "agent_question");

const completionsOnly = await fixture({ attention_notifications: false, success_notifications: true }, [success, approval]);
await completionsOnly.poll();
assert.deepEqual(completionsOnly.shown.map(notification => notification.options.title), [success.title], "Completed work has its own notification preference");
assert.equal(completionsOnly.opened, 0, "delivery never foregrounds the application");
completionsOnly.shown[0].handlers.click();
assert.equal(completionsOnly.opened, 1);
assert.deepEqual(completionsOnly.messages, [["workbench:attention", null, success.run_id]], "activation retains the non-Chat run identity");

const attentionOnly = await fixture({ attention_notifications: true, success_notifications: false }, [success, approval, question]);
await attentionOnly.poll();
assert.deepEqual(attentionOnly.shown.map(notification => notification.options.title), [approval.title, question.title], "attention preference does not enable completion notices");
attentionOnly.shown[0].handlers.click();
assert.deepEqual(attentionOnly.messages, [["workbench:attention", approval.conversation_id, approval.run_id]], "Chat activation retains its conversation and run identity");
await attentionOnly.poll();
assert.equal(attentionOnly.shown.length, 2, "repeated polls cannot deliver duplicate notifications");

const foreground = await fixture({ attention_notifications: true, success_notifications: true }, [approval], { focused: true });
await foreground.poll();
assert.equal(foreground.shown.length, 0);
assert.equal(foreground.claims.length, 0, "viewing the application does not consume a later background notification");
foreground.focused = false;
await foreground.poll();
assert.equal(foreground.shown.length, 1);

const alreadyClaimed = await fixture({ attention_notifications: true, success_notifications: true }, [approval], { claimAllowed: false });
await alreadyClaimed.poll();
assert.equal(alreadyClaimed.shown.length, 0, "another desktop instance's durable claim prevents duplicate delivery");

const unavailable = await fixture({ attention_notifications: true, success_notifications: true }, [approval], { supported: false });
await unavailable.poll();
assert.equal(unavailable.shown.length, 0);
assert.equal(unavailable.claims.length, 0, "an unsupported OS leaves the item available to the in-app Attention list");

console.log("Background notification checks passed.");

function item(kind, conversationId, runId) {
  return { identity: `${runId}:${kind}:1`, kind, title: `${kind} item`, run_id: runId, conversation_id: conversationId, notified: false };
}

async function fixture(preferences, items, options = {}) {
  const state = { shown: [], messages: [], claims: [], opened: 0, focused: options.focused ?? false };
  let poll;
  class Tray {
    setToolTip() {}
    setContextMenu() {}
    on() {}
  }
  class Notification {
    static isSupported() { return options.supported ?? true; }
    constructor(notificationOptions) { this.options = notificationOptions; this.handlers = {}; }
    on(name, callback) { this.handlers[name] = callback; }
    show() { state.shown.push(this); }
  }
  const electron = {
    app: { getFileIcon: async () => ({}), on() {} },
    BrowserWindow: { getAllWindows: () => [{ isFocused: () => state.focused, isVisible: () => true, webContents: { send: (...args) => state.messages.push(args) } }] },
    dialog: {}, ipcMain: { handle() {} }, Menu: { buildFromTemplate: value => value }, Notification, Tray,
  };
  const context = {
    exports: {}, process, console, AbortSignal, URLSearchParams, Buffer,
    require: id => id === "electron" ? electron
      : id === "./localTrust" ? { ensureSharedSecret: () => "test-token", resolveProductDataRoot: () => "unused", WORKBENCH_BACKEND_ORIGIN: "http://fixture", WORKBENCH_LOCAL_TOKEN_HEADER: "token" }
        : id === "./trustBoundary" ? {} : require(id),
    setInterval: callback => { poll = callback; return 1; }, clearInterval() {},
    fetch: async url => {
      let body;
      if (url.endsWith("/claim")) { state.claims.push(url); body = { claimed: options.claimAllowed ?? true }; }
      else if (url.endsWith("settings/presentation")) body = preferences;
      else body = items;
      return { ok: true, json: async () => body };
    },
  };
  vm.runInNewContext(`${source}\nexports.pollAttentionForTest = pollAttention;`, context);
  await context.exports.installBackground(() => { state.opened += 1; });
  assert.ok(poll, "background installation schedules attention polling");
  state.poll = () => context.exports.pollAttentionForTest(() => { state.opened += 1; });
  return state;
}
