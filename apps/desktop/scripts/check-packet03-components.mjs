import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";

import React from "react";
import { act, create } from "react-test-renderer";
import { createServer as createViteServer } from "vite";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const desktopRoot = path.join(repoRoot, "apps/desktop");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

globalThis.window = {
  workbench: {
    saveAsset: async () => "C:\\Temp\\saved.txt",
  },
};

const vite = await createViteServer({ root: desktopRoot, appType: "custom", server: { middlewareMode: true, hmr: false }, logLevel: "error" });
try {
  const { ComposerAttachments } = await vite.ssrLoadModule("/src/renderer/ComposerAttachments.tsx");
  const { LibraryPanel } = await vite.ssrLoadModule("/src/renderer/LibraryPanel.tsx");

  await checkComposerUploadStaleGuard(ComposerAttachments);
  await checkLibraryStalePreviewAndScopedCalls(LibraryPanel);
} finally {
  await vite.close();
}

console.log("Packet03 component checks passed.");

async function checkComposerUploadStaleGuard(ComposerAttachments) {
  const originalFetch = globalThis.fetch;
  const uploads = new Map();
  globalThis.fetch = async (url, init) => {
    assert.match(String(url), /\/v1\/assets\/uploads$/);
    const body = JSON.parse(String(init.body));
    const deferred = createDeferred();
    uploads.set(body.session_id, { body, deferred });
    return deferred.promise;
  };

  try {
    const attachments = [];
    let renderer;
    await act(async () => {
      renderer = create(React.createElement(ComposerAttachments, {
        sessionId: "chat_old",
        onAttachmentsChanged: (next) => attachments.push(next.map((item) => item.id)),
      }));
    });

    await act(async () => {
      input(renderer, "file").props.onChange({ target: { files: [new File(["old"], "old.txt", { type: "text/plain" })] }, currentTarget: { value: "" } });
      await tick();
    });
    assert.equal(uploads.get("chat_old").body.content_base64, "b2xk");

    await act(async () => {
      renderer.update(React.createElement(ComposerAttachments, {
        sessionId: "chat_new",
        onAttachmentsChanged: (next) => attachments.push(next.map((item) => item.id)),
      }));
    });
    await act(async () => {
      input(renderer, "file").props.onChange({ target: { files: [new File(["new"], "new.ts", { type: "text/plain" })] }, currentTarget: { value: "" } });
      await tick();
    });

    uploads.get("chat_old").deferred.resolve(jsonResponse(asset("asset_old", "old.txt", "chat_old")));
    await act(async () => {
      await tick();
    });
    assert.ok(!textOf(renderer.root).includes("asset_old"), "stale upload response from previous session must not stage an attachment");

    uploads.get("chat_new").deferred.resolve(jsonResponse(asset("asset_new", "new.ts", "chat_new")));
    await act(async () => {
      await tick();
    });
    assert.ok(textOf(renderer.root).includes("asset_new"), "current upload should stage retained asset id");
    assert.deepEqual(attachments.at(-1), ["asset_new"]);

    await act(async () => {
      button(renderer, "Remove from draft").props.onClick();
    });
    assert.deepEqual(attachments.at(-1), [], "removing staged attachment should only update parent draft attachments");
  } finally {
    globalThis.fetch = originalFetch;
  }
}

async function checkLibraryStalePreviewAndScopedCalls(LibraryPanel) {
  const originalFetch = globalThis.fetch;
  const previewCalls = [];
  const previewDefers = new Map();
  let deleteRequestedIds = null;
  globalThis.fetch = async (url, init) => {
    const address = String(url);
    if (address.includes("/v1/assets/delete-preview")) {
      return jsonResponse({
        requested_asset_ids: ["asset_a", "asset_b"],
        affected_asset_ids: ["asset_a"],
        preserved_asset_ids: ["asset_b"],
        affected_sessions: [],
        retained_sessions: [],
        affected_runs: [],
        retained_runs: [],
        affected_projects: [],
        retained_projects: [],
        affected_branches: [],
        retained_branches: [],
        affected_cases: [],
        retained_cases: ["case_1"],
        note: "Preview only.",
      });
    }
    if (address.includes("/v1/assets/delete")) {
      deleteRequestedIds = JSON.parse(String(init.body)).asset_ids;
      return jsonResponse({
        requested_asset_ids: deleteRequestedIds,
        affected_asset_ids: ["asset_a"],
        preserved_asset_ids: ["asset_b"],
        affected_sessions: [],
        retained_sessions: [],
        affected_runs: [],
        retained_runs: [],
        affected_projects: [],
        retained_projects: [],
        affected_branches: [],
        retained_branches: [],
        affected_cases: [],
        retained_cases: ["case_1"],
        note: "Deleted what was safe.",
      });
    }
    if (address.includes("/v1/assets/asset_a/content")) {
      return jsonResponse({
        id: "asset_a",
        filename: "a.txt",
        content_type: "text/plain",
        encoding: "utf-8",
        text: "full retained text",
        sha256: "sha",
        size_bytes: 18,
        source_status: "changed",
      });
    }
    if (address.includes("/preview")) {
      const id = address.includes("asset_a") ? "asset_a" : "asset_b";
      const deferred = createDeferred();
      previewCalls.push({ id, address });
      previewDefers.set(id, deferred);
      return deferred.promise;
    }
    if (address.includes("/v1/assets")) {
      return jsonResponse([
        asset("asset_a", "a.txt", "source_session", { source_status: "changed" }),
        asset("asset_b", "b.txt", "other_session", { project_path: "D:\\Project", source_status: "unchanged" }),
      ]);
    }
    throw new Error(`unexpected fetch ${address}`);
  };

  try {
    let renderer;
    await act(async () => {
      renderer = create(React.createElement(LibraryPanel, { sessionId: "current_session", projectPath: null }));
      await tick();
    });
    await act(async () => {
      await tick();
    });

    assert.ok(button(renderer, "Reuse selected").props.disabled, "reuse must be disabled without a destination callback");

    await act(async () => {
      button(renderer, "Preview").props.onClick();
      await tick();
    });
    assert.ok(previewCalls.at(-1).address.includes("session_id=source_session"), "preview should use selected asset source session scope");

    const previewButtons = renderer.root.findAll((node) => node.type === "button" && textOf(node).includes("Preview"));
    await act(async () => {
      previewButtons[1].props.onClick();
      await tick();
    });
    assert.ok(previewCalls.at(-1).address.includes("session_id=other_session"), "all-retained preview should not omit access scope");

    previewDefers.get("asset_b").resolve(jsonResponse({
      id: "asset_b",
      filename: "b.txt",
      content_type: "text/plain",
      size_bytes: 6,
      sha256: "sha",
      preview: "second",
      truncated: false,
      source_status: "unchanged",
    }));
    await act(async () => {
      await tick();
    });
    previewDefers.get("asset_a").resolve(jsonResponse({
      id: "asset_a",
      filename: "a.txt",
      content_type: "text/plain",
      size_bytes: 5,
      sha256: "sha",
      preview: "first",
      truncated: false,
      source_status: "changed",
    }));
    await act(async () => {
      await tick();
    });
    assert.ok(textOf(renderer.root).includes("second"), "latest preview should stay visible");
    assert.ok(!textOf(renderer.root).includes("first"), "stale preview response should be ignored");

    await act(async () => {
      button(renderer, "Open full text").props.onClick();
      await tick();
    });
    assert.ok(textOf(renderer.root).includes("full retained text"));
    assert.ok(textOf(renderer.root).includes("Source changed; showing retained copy"));

    const checkboxes = renderer.root.findAll((node) => node.type === "input" && node.props.type === "checkbox");
    await act(async () => {
      checkboxes[0].props.onChange({ target: { checked: true } });
      checkboxes[1].props.onChange({ target: { checked: true } });
    });
    await act(async () => {
      button(renderer, "Preview delete").props.onClick();
      await tick();
    });
    await act(async () => {
      button(renderer, "Delete affected retained copies").props.onClick();
      await tick();
    });
    assert.deepEqual(deleteRequestedIds, ["asset_a"], "delete confirmation must request only deletable affected ids");
    assert.ok(textOf(renderer.root).includes("1 shared item preserved"));
  } finally {
    globalThis.fetch = originalFetch;
  }
}

function asset(id, filename, sessionId, overrides = {}) {
  return {
    id,
    origin: "upload",
    scope: "session",
    session_id: sessionId,
    project_path: null,
    access_scope: `session:${sessionId}`,
    storage: "application.sqlite",
    filename,
    content_type: "text/plain",
    content_kind: "text",
    encoding: "utf-8",
    size_bytes: filename.length,
    sha256: "sha",
    observed_at: "2026-09-21T00:00:00Z",
    source_run_id: null,
    source_tool_call_id: null,
    source_tool_name: null,
    mutable_reference: null,
    observation: null,
    deleted_at: null,
    ...overrides,
  };
}

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function createDeferred() {
  let resolve;
  let reject;
  const promise = new Promise((innerResolve, innerReject) => {
    resolve = innerResolve;
    reject = innerReject;
  });
  return { promise, resolve, reject };
}

async function tick() {
  await Promise.resolve();
  await Promise.resolve();
}

function input(renderer, type) {
  const found = renderer.root.findAll((node) => node.type === "input" && node.props.type === type);
  assert.ok(found.length > 0, `expected input ${type}`);
  return found[0];
}

function button(renderer, label) {
  const found = renderer.root.findAll((node) => node.type === "button" && textOf(node).includes(label));
  assert.ok(found.length > 0, `expected button ${label}`);
  return found[0];
}

function textOf(value) {
  if (value == null || typeof value === "boolean") {
    return "";
  }
  if (typeof value === "string" || typeof value === "number") {
    return String(value);
  }
  if (Array.isArray(value)) {
    return value.map(textOf).join("");
  }
  if (value.children) {
    return textOf(value.children);
  }
  return "";
}
