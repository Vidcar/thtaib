import React from "react";
import { createRoot } from "react-dom/client";
import { SourceLink, SourceScope } from "../../src/renderer/SourceReference";
import { ImagePreview } from "../../src/renderer/ImagePreview";
import { LibraryPanel } from "../../src/renderer/LibraryPanel";
import "../../src/renderer/appearanceDefaults.css";
import "../../src/renderer/styles.css";

const sha = "a".repeat(64);
const imageData = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jB9kAAAAASUVORK5CYII=";
Object.assign(window, { workbench: { backendUrl: "http://fixture.invalid", saveAsset: async () => { window.fixture.saved++; } }, fixture: { saved: 0, calls: [] } });
window.fetch = async (url, init) => {
  const address = new URL(String(url));
  if (address.pathname === "/v1/assets") return { ok: true, json: async () => [{ id: "asset_image", filename: "Library image.png", session_id: "chat_fixture", content_kind: "image", content_type: "image/png", size_bytes: 90, origin: "upload", observed_at: "2026-09-22T12:00:00Z" }] } as Response;
  if (address.pathname === "/v1/assets/asset_image/preview") return { ok: true, json: async () => ({ id: "asset_image", filename: "Library image.png", size_bytes: 90, source_status: "retained_only", image_data_url: imageData }) } as Response;
  if (address.pathname === "/v1/assets/asset_image/content") return { ok: true, json: () => new Promise(resolve => { window.fixture.resolveOriginal = () => resolve({ content_type: "image/png", content_base64: imageData.split(",")[1] }); }) } as Response;
  const input = JSON.parse(init?.body as string);
  window.fixture.calls.push(input);
  if (String(url).includes("asset_error")) return { ok: false, status: 404, json: async () => ({ error: "This source is unavailable in the selected conversation." }) } as Response;
  return { ok: true, json: async () => ({ filename: "Long retained research notes — exact original version.docx", sha256: sha, source: "Paragraph 24 · Selected introduction", extracted_line: input.extracted_line, start_char: input.start_char, end_char: input.end_char, text: "This is the actual selected source passage.\n" + Array.from({ length: 80 }, (_, index) => `${index + 1}. Long source text with a very long address https://example.test/${"long-path/".repeat(30)}.`).join("\n"), truncated: true, parser: "python-docx" }) } as Response;
};
const root = createRoot(document.getElementById("root")!);
window.fixture.showLibrary = () => root.render(<main style={{ padding: 20 }}><LibraryPanel /></main>);
root.render(<main style={{ padding: 20 }}><SourceScope.Provider value={{ sessionId: "chat_fixture" }}><p><SourceLink href={`workbench-source://asset_ready/${sha}?source=Paragraph%2024&line=24&start=12&end=120`}>Read selected passage</SourceLink></p><p><SourceLink href={`workbench-source://asset_error/${sha}?source=Page%203&line=3&start=0&end=100`}>Read missing passage</SourceLink></p></SourceScope.Provider><button type="button">Next focus target</button><ImagePreview name="Retained image" src={imageData} /></main>);
