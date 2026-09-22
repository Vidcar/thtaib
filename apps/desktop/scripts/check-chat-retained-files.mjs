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
    backendUrl: "http://retained-files.test",
    saveAsset: async () => "saved.txt",
  },
};

const vite = await createViteServer({ root: desktopRoot, appType: "custom", server: { middlewareMode: true, hmr: false }, logLevel: "error" });
try {
  const { ChatRetainedFiles } = await vite.ssrLoadModule("/src/renderer/ChatRetainedFiles.tsx");
  const { LibraryPanel } = await vite.ssrLoadModule("/src/renderer/LibraryPanel.tsx");
  await checkInlineRunFilteringAndReuse(ChatRetainedFiles);
  await checkPreviewRaceKeepsLatestSelection(ChatRetainedFiles);
  await checkTerminalStatusRefreshesSelfFetchedAssets(ChatRetainedFiles);
  await checkLibraryMultiSelectReuse(LibraryPanel);
} finally {
  await vite.close();
}

console.log("Chat retained files checks passed.");

async function checkInlineRunFilteringAndReuse(ChatRetainedFiles) {
  const reused = [];
  let opened = [];
  let renderer;
  const restore = mockFetch(async (url) => {
    assert.match(String(url), /\/v1\/assets\/asset_output\/preview\?session_id=chat_1/);
    return preview("asset_output", "Source changed; retained text", "changed");
  });
  try {
    await act(async () => {
      renderer = create(React.createElement(ChatRetainedFiles, {
        conversationId: "chat_1",
        runIds: ["run_2"],
        currentRunId: "run_2",
        currentRunStatus: "completed",
        records: [
          asset("asset_old", "old.txt", "run_1"),
          asset("asset_output", "answer.txt", "run_2", { origin: "verified_output", session_id: "chat_origin", mutable_reference: "answer.txt", source_tool_name: "write_file" }),
        ],
        onReuse: (assetIds) => reused.push(assetIds),
        onOpenFiles: (assetIds) => { opened = assetIds; },
      }));
    });
    const text = textOf(renderer.toJSON());
    assert.match(text, /answer.txt/, "matching run asset should render");
    assert.doesNotMatch(text, /old.txt/, "non-matching run asset should be hidden beside this reply");
    assert.doesNotMatch(text, /run_2|asset_output/, "raw run and asset ids should not be foreground text");
    await act(async () => {
      input(renderer, "checkbox").props.onChange({ target: { checked: true } });
    });
    await act(async () => {
      button(renderer, "Reuse selected").props.onClick();
    });
    assert.deepEqual(reused.at(-1), ["asset_output"], "inline reuse should return selected asset ids");
    await act(async () => {
      button(renderer, "Preview").props.onClick();
    });
    assert.match(textOf(renderer.toJSON()), /Source changed; retained copy preserved/, "preview should update source change state");
    await act(async () => {
      button(renderer, "Open text").props.onClick();
    });
    assert.deepEqual(opened, ["asset_output"], "open action should report opened asset ids to the parent");
  } finally {
    restore();
  }
}

async function checkPreviewRaceKeepsLatestSelection(ChatRetainedFiles) {
  const first = deferred();
  const second = deferred();
  const restore = mockFetch(async (url) => {
    if (String(url).includes("asset_first")) {
      await first.promise;
      return preview("asset_first", "first retained text", "unchanged");
    }
    if (String(url).includes("asset_second")) {
      await second.promise;
      return preview("asset_second", "second retained text", "retained_only");
    }
    throw new Error(`unexpected url ${url}`);
  });
  let renderer;
  try {
    await act(async () => {
      renderer = create(React.createElement(ChatRetainedFiles, {
        conversationId: "chat_1",
        runIds: ["run_2"],
        records: [
          asset("asset_first", "first.txt", "run_2"),
          asset("asset_second", "second.txt", "run_2"),
        ],
        onReuse: () => {},
      }));
    });
    const previewButtons = renderer.root.findAll((node) => node.type === "button" && textOf(node).trim() === "Preview");
    await act(async () => {
      previewButtons[0].props.onClick();
    });
    await act(async () => {
      previewButtons[1].props.onClick();
    });
    await act(async () => {
      second.resolve();
      await second.promise;
    });
    assert.match(textOf(renderer.toJSON()), /second retained text/, "newer preview should render first when it resolves first");
    await act(async () => {
      first.resolve();
      await first.promise;
    });
    assert.match(textOf(renderer.toJSON()), /second retained text/, "late earlier preview must not overwrite the selected newer preview");
    assert.doesNotMatch(textOf(renderer.toJSON()), /first retained text/, "stale preview result should stay hidden");
  } finally {
    restore();
  }
}

async function checkLibraryMultiSelectReuse(LibraryPanel) {
  const reused = [];
  const restore = mockFetch(async (url) => {
    assert.match(String(url), /\/v1\/assets(?:\?|$)/);
    return [
      asset("asset_one", "one.txt", null),
      asset("asset_two", "two.txt", null),
    ];
  });
  let renderer;
  try {
    await act(async () => {
      renderer = create(React.createElement(LibraryPanel, {
        onReuseSelectedAssets: (assets) => reused.push(assets.map((asset) => asset.id)),
      }));
    });
    await act(async () => {
      await Promise.resolve();
    });
    const checks = assetCheckboxes(renderer);
    assert.ok(checks.length >= 2, "library should render selectable retained assets");
    await act(async () => {
      checks[0].props.onChange({ target: { checked: true } });
    });
    const updatedChecks = assetCheckboxes(renderer);
    await act(async () => {
      updatedChecks[1].props.onChange({ target: { checked: true } });
    });
    await act(async () => {
      button(renderer, "Reuse selected").props.onClick();
    });
    assert.deepEqual(reused.at(-1), ["asset_one", "asset_two"], "library reuse should preserve the full multi-selection");
  } finally {
    restore();
  }
}

async function checkTerminalStatusRefreshesSelfFetchedAssets(ChatRetainedFiles) {
  let calls = 0;
  const restore = mockFetch(async (url) => {
    assert.match(String(url), /\/v1\/assets\?session_id=chat_1/);
    calls += 1;
    return calls < 2 ? [] : [asset("asset_done", "done.txt", "run_done")];
  });
  let renderer;
  try {
    await act(async () => {
      renderer = create(React.createElement(ChatRetainedFiles, {
        conversationId: "chat_1",
        currentRunId: "run_done",
        currentRunStatus: "running",
        onReuse: () => {},
      }));
    });
    await act(async () => {
      await Promise.resolve();
    });
    assert.equal(calls, 1, "self-fetching retained files should load once on mount");
    await act(async () => {
      renderer.update(React.createElement(ChatRetainedFiles, {
        conversationId: "chat_1",
        currentRunId: "run_done",
        currentRunStatus: "completed",
        onReuse: () => {},
      }));
    });
    await act(async () => {
      await Promise.resolve();
    });
    assert.equal(calls, 2, "terminal run status should trigger one retained asset refresh");
    assert.match(textOf(renderer.toJSON()), /done.txt/, "terminal refresh should render collected retained output");
  } finally {
    restore();
  }
}

function assetCheckboxes(renderer) {
  return renderer.root.findAll((node) => (
    node.type === "input" &&
    node.props.type === "checkbox" &&
    !node.props.disabled &&
    node.parent?.findAllByType("strong").length > 0
  ));
}

function asset(id, filename, runId, overrides = {}) {
  return {
    id,
    origin: "upload",
    scope: "session",
    session_id: "chat_1",
    project_path: null,
    access_scope: "session:chat_1",
    storage: "application.sqlite",
    filename,
    content_type: "text/plain",
    content_kind: "text",
    encoding: "utf-8",
    size_bytes: 32,
    sha256: "abc",
    observed_at: "2026-09-21T00:00:00Z",
    source_run_id: runId,
    source_tool_call_id: null,
    source_tool_name: null,
    mutable_reference: null,
    observation: null,
    deleted_at: null,
    ...overrides,
  };
}

function preview(id, text, sourceStatus) {
  return {
    id,
    filename: "answer.txt",
    content_type: "text/plain",
    size_bytes: text.length,
    sha256: "abc",
    preview: text,
    truncated: false,
    source_status: sourceStatus,
    encoding: "utf-8",
    text,
  };
}

function mockFetch(handler) {
  const previous = globalThis.fetch;
  globalThis.fetch = async (url) => ({
    ok: true,
    json: async () => handler(url),
  });
  return () => {
    globalThis.fetch = previous;
  };
}

function deferred() {
  let resolve;
  const promise = new Promise((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

function input(renderer, type) {
  const found = renderer.root.findAll((node) => node.type === "input" && node.props.type === type);
  assert.ok(found.length > 0, `expected input ${type}`);
  return found[0];
}

function button(renderer, label) {
  const found = renderer.root.findAll((node) => node.type === "button" && textOf(node).trim() === label);
  assert.ok(found.length > 0, `expected button ${label}`);
  return found[0];
}

function textOf(node) {
  if (typeof node === "string") {
    return node;
  }
  if (!node?.children) {
    return "";
  }
  return node.children.map(textOf).join("");
}
