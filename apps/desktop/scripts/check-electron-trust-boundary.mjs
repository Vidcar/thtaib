import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";
import { createServer as createViteServer } from "vite";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const desktopRoot = path.resolve(scriptDir, "..");
const repoRoot = path.resolve(desktopRoot, "../..");
const electronBin = process.platform === "win32"
  ? path.join(desktopRoot, "node_modules/electron/dist/electron.exe")
  : path.join(desktopRoot, "node_modules/electron/dist/electron");

assert.ok(existsSync(electronBin), `Electron binary not found at ${electronBin}`);

const scratch = path.join(repoRoot, ".scratch/electron-trust-boundary");
mkdirSync(scratch, { recursive: true });
const compiledTrustBoundary = compileMainModule("trustBoundary.ts");
compileMainModule("localTrust.ts");
const markdownHtml = await renderMarkdownFixtureHtml();

const fixtureMain = path.join(scratch, "fixture-main.mjs");
writeFileSync(fixtureMain, fixtureSource(compiledTrustBoundary, markdownHtml), "utf8");
writeFileSync(path.join(scratch, "package.json"), JSON.stringify({ type: "module", main: "fixture-main.mjs" }), "utf8");

const vulnerable = await runFixture("vulnerable");
assert.equal(vulnerable.captures["dev:trusted"], "electron-boundary-token", "vulnerable baseline should authenticate trusted app request");
assert.equal(vulnerable.captures["dev:untrusted-window"], "electron-boundary-token", "vulnerable baseline must reproduce untrusted same-session token injection");
assert.equal(vulnerable.captures["dev:iframe"], "electron-boundary-token", "vulnerable baseline must reproduce untrusted frame token injection");
assert.ok(vulnerable.replacedUrls.dev.endsWith("/replacement"), "vulnerable baseline should allow replacing the app document");
assert.ok(vulnerable.openWindowCounts.dev > 0, "vulnerable baseline should create an in-app window for external links");

const fixed = await runFixture("fixed");
writeFileSync(path.join(scratch, "receiver-results.json"), JSON.stringify({ vulnerable, fixed }, null, 2));
for (const mode of ["dev", "file"]) {
  assert.equal(fixed.captures[`${mode}:trusted`], "electron-boundary-token", `${mode} trusted app request should receive token`);
  assert.equal(fixed.captures[`${mode}:iframe`], "", `${mode} untrusted subframe should not receive token`);
  assert.equal(fixed.captures[`${mode}:untrusted-window`], "", `${mode} untrusted window should not receive token`);
  assert.equal(fixed.captures[`${mode}:untrusted-spoofed`], "", `${mode} untrusted request should strip caller-supplied token`);
  assert.equal(fixed.captures[`${mode}:registered-replaced`], "", `${mode} replaced trusted-window document should not receive token`);
  assert.equal(fixed.forwardedCaptures[`${mode}:redirect-forward`], "", `${mode} backend redirect must not forward token to another receiver`);
  assert.equal(fixed.redirectUrls[mode], fixed.expectedUrls[mode], `${mode} redirected navigation should retain original trusted document`);
  assert.equal(fixed.replacedUrls[mode], fixed.expectedUrls[mode], `${mode} same-origin replacement should be denied`);
  assert.equal(fixed.externalOpens[mode].length, mode === "dev" ? 3 : 1, `${mode} opens only resolved HTTP(S) links`);
  assert.equal(fixed.externalOpens[mode][0], fixed.externalUrls[mode], `${mode} should route external Markdown link to system browser`);
  assert.equal(fixed.openWindowCounts[mode], 0, `${mode} external Markdown link should not create an in-app BrowserWindow`);
  assert.deepEqual(fixed.blockedLinks[mode].sort(), ["custom", "file", "protocol", "relative"].sort(), `${mode} unsafe link forms should not be rendered as anchors`);
}

console.log("Electron trust-boundary fixture passed");
console.log("Vulnerable reproduction:", JSON.stringify({
  untrustedWindowHeader: vulnerable.captures["dev:untrusted-window"],
  iframeHeader: vulnerable.captures["dev:iframe"],
  replacedUrl: vulnerable.replacedUrls.dev,
  inAppWindows: vulnerable.openWindowCounts.dev,
}));
console.log("Fixed boundary:", JSON.stringify({
  trustedDevHeader: fixed.captures["dev:trusted"],
  untrustedDevHeader: fixed.captures["dev:untrusted-window"],
  fileIframeHeader: fixed.captures["file:iframe"],
  externalOpenDev: fixed.externalOpens.dev,
  externalOpenFile: fixed.externalOpens.file,
}));

async function renderMarkdownFixtureHtml() {
  const vite = await createViteServer({ root: desktopRoot, appType: "custom", server: { middlewareMode: true, hmr: false }, logLevel: "error" });
  try {
    const { AgentMessageFeed } = await vite.ssrLoadModule("/src/renderer/AgentMessageFeed.tsx");
    return renderToStaticMarkup(
      React.createElement(AgentMessageFeed, {
        messages: [{
          id: "link-fixture",
          content: [
            [
              "[external](https://example.invalid/markdown-external)",
              "[relative](/relative)",
              "[protocol](//example.invalid/protocol-relative)",
              "[file](file:///C:/Windows/notepad.exe)",
              "[custom](vscode://file/test)",
            ].join(" "),
          ],
          getType() {
            return "ai";
          },
        }],
      }),
    );
  } finally {
    await vite.close();
  }
}

async function runFixture(boundaryMode) {
  const child = spawn(electronBin, [scratch], {
    cwd: scratch,
    env: {
      ...process.env,
      ELECTRON_DISABLE_SECURITY_WARNINGS: "true",
      WORKBENCH_BOUNDARY_MODE: boundaryMode,
    },
    stdio: ["ignore", "pipe", "pipe"],
  });

  let stdout = "";
  let stderr = "";
  child.stdout.setEncoding("utf8");
  child.stderr.setEncoding("utf8");
  child.stdout.on("data", (chunk) => {
    stdout += chunk;
  });
  child.stderr.on("data", (chunk) => {
    stderr += chunk;
  });
  const timeout = setTimeout(() => {
    child.kill();
  }, 45000);
  const exitCode = await new Promise((resolve) => {
    child.on("exit", (code) => resolve(code));
  });
  clearTimeout(timeout);
  if (exitCode !== 0) {
    throw new Error(`Electron ${boundaryMode} fixture failed with ${exitCode}\nSTDOUT:\n${stdout}\nSTDERR:\n${stderr}`);
  }
  const resultLine = stdout.trim().split(/\r?\n/).find((line) => line.startsWith("TRUST_BOUNDARY_RESULT "));
  assert.ok(resultLine, `Fixture did not report a result\nSTDOUT:\n${stdout}\nSTDERR:\n${stderr}`);
  return JSON.parse(resultLine.slice("TRUST_BOUNDARY_RESULT ".length));
}

function fixtureSource(trustBoundaryPath, renderedMarkdownHtml) {
  const trustBoundaryUrl = pathToFileURL(trustBoundaryPath).toString();
  return `
import { writeFileSync } from "node:fs";
import http from "node:http";
import path from "node:path";
import assert from "node:assert/strict";
import { app, BrowserWindow, session, shell } from "electron";
import {
  installLocalTrustHeader,
  installTrustedAppWindow,
  packagedAppDocumentUrl,
  isTrustedBackendRequest,
} from ${JSON.stringify(trustBoundaryUrl)};

console.log("fixture boot", process.env.WORKBENCH_BOUNDARY_MODE);
const TOKEN = "electron-boundary-token";
const boundaryMode = process.env.WORKBENCH_BOUNDARY_MODE ?? "fixed";
const markdownHtml = ${JSON.stringify(renderedMarkdownHtml)};
const captures = {};
const forwardedCaptures = {};
const externalOpens = { dev: [], file: [] };
const externalUrls = {};
const expectedUrls = {};
const openWindowCounts = {};
const blockedLinks = {};
const redirectUrls = {};
const replacedUrls = {};
let activeMode = "dev";

app.commandLine.appendSwitch("disable-gpu");
app.commandLine.appendSwitch("disable-background-timer-throttling");
app.on("window-all-closed", () => {});

void app.whenReady().then(main).catch((error) => {
  console.error(error);
  app.exit(1);
});

let backendOrigin = "";
let externalOrigin = "";
let appOrigin = "";

async function main() {
  console.log("fixture ready", boundaryMode);
  const externalReceiver = await listen((request, response) => {
    const url = new URL(request.url ?? "/", "http://127.0.0.1");
    const key = url.searchParams.get("case") ?? "unknown";
    forwardedCaptures[key] = request.headers["x-workbench-local-token"] ?? "";
    response.setHeader("Access-Control-Allow-Origin", "*");
    response.setHeader("Access-Control-Allow-Headers", "*");
    response.end("ok");
  });
  externalOrigin = "http://127.0.0.1:" + externalReceiver.port;
  console.log("fixture external", externalOrigin);

  const backend = await listen((request, response) => {
    const url = new URL(request.url ?? "/", "http://127.0.0.1");
    if (url.pathname === "/redirect-token") {
      response.statusCode = 302;
      response.setHeader("Location", externalOrigin + "/capture?case=" + encodeURIComponent(url.searchParams.get("case") ?? "redirect"));
      response.end();
      return;
    }
    const key = url.searchParams.get("case") ?? "unknown";
    captures[key] = request.headers["x-workbench-local-token"] ?? "";
    response.setHeader("Access-Control-Allow-Origin", "*");
    response.setHeader("Access-Control-Allow-Headers", "*");
    response.end("ok");
  });
  backendOrigin = "http://127.0.0.1:" + backend.port;
  console.log("fixture backend", backendOrigin);

  const appServer = await listen((request, response) => {
    const requestUrl = request.url ?? "/";
    if (requestUrl.startsWith("/redirect")) {
      response.statusCode = 302;
      response.setHeader("Location", "https://example.invalid/redirected");
      response.end();
      return;
    }
    response.setHeader("Content-Type", "text/html; charset=utf-8");
    response.end("<!doctype html><title>trusted</title><main>trusted app</main>");
  });
  appOrigin = "http://127.0.0.1:" + appServer.port;
  console.log("fixture app server", appOrigin);

  shell.openExternal = async (url) => {
    externalOpens[activeMode].push(url);
    return "";
  };

  if (boundaryMode === "fixed") {
    installLocalTrustHeader(TOKEN, backendOrigin);
  } else {
    session.defaultSession.webRequest.onBeforeSendHeaders({ urls: [backendOrigin + "/*"] }, (details, callback) => {
      callback({ requestHeaders: { ...details.requestHeaders, "X-Workbench-Local-Token": TOKEN } });
    });
  }

  try {
    await runMode("dev", appOrigin + "/", appOrigin + "/replacement", false);
    if (boundaryMode === "fixed") {
      const filePath = path.join(process.cwd(), "trusted-file.html");
      const replacementPath = path.join(process.cwd(), "replacement-file.html");
      writeFileSync(filePath, "<!doctype html><title>trusted-file</title><main>trusted file</main>", "utf8");
      writeFileSync(replacementPath, "<!doctype html><title>replacement-file</title><main>replacement file</main>", "utf8");
      await runMode("file", packagedAppDocumentUrl(filePath), packagedAppDocumentUrl(replacementPath), false);
    }
    console.log("TRUST_BOUNDARY_RESULT " + JSON.stringify({
      captures,
      forwardedCaptures,
      externalOpens,
      externalUrls,
      expectedUrls,
      openWindowCounts,
      blockedLinks,
      redirectUrls,
      replacedUrls,
    }));
    app.quit();
  } catch (error) {
    console.error(error);
    app.exit(1);
  } finally {
    backend.server.close();
    externalReceiver.server.close();
    appServer.server.close();
  }
}

async function runMode(mode, appUrl, replacementUrl, useProtocolRelativeExternal) {
  console.log("fixture step", boundaryMode, mode, "start");
  activeMode = mode;
  expectedUrls[mode] = appUrl;
  const trusted = new BrowserWindow({ show: false, webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true } });
  if (boundaryMode === "fixed") {
    installTrustedAppWindow(trusted, { appUrl, backendOrigin });
  }
  await trusted.loadURL(appUrl);
  console.log("fixture step", boundaryMode, mode, "loaded");
  await fetchFrom(trusted, mode + ":trusted");
  console.log("fixture step", boundaryMode, mode, "trusted fetch");
  await fetchRedirectForward(trusted, mode + ":redirect-forward");
  console.log("fixture step", boundaryMode, mode, "redirect fetch");
  await fetchFromIframe(trusted, mode + ":iframe");
  console.log("fixture step", boundaryMode, mode, "iframe fetch");

  const windowsBeforeLink = BrowserWindow.getAllWindows().length;
  const createdWindow = boundaryMode === "vulnerable"
    ? new Promise((resolve) => trusted.webContents.once("did-create-window", resolve)) : null;
  externalUrls[mode] = useProtocolRelativeExternal ? "https://example.invalid/protocol-relative" : "https://example.invalid/markdown-external";
  await installMarkdownAndActivateLinks(trusted, useProtocolRelativeExternal);
  console.log("fixture step", boundaryMode, mode, "links activated");
  if (boundaryMode === "fixed") {
    await waitFor(() => externalOpens[mode].length >= 1, mode + " external open");
  } else {
    await createdWindow;
  }
  openWindowCounts[mode] = BrowserWindow.getAllWindows().length - windowsBeforeLink;

  try { await trusted.loadURL(appOrigin + "/redirect"); } catch {}
  redirectUrls[mode] = trusted.webContents.getURL();
  console.log("fixture step", boundaryMode, mode, "redirect nav", redirectUrls[mode]);

  await navigateFromRenderer(trusted, replacementUrl);
  replacedUrls[mode] = trusted.webContents.getURL();
  console.log("fixture step", boundaryMode, mode, "replacement nav", replacedUrls[mode]);
  // Main-process replacement bypasses renderer navigation interception. Token
  // authorization must independently reject this formerly trusted window.
  await trusted.loadURL(replacementUrl);
  await fetchFrom(trusted, mode + ":registered-replaced");
  console.log("fixture step", boundaryMode, mode, "replaced fetch");

  const untrusted = new BrowserWindow({ show: false, webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true } });
  await untrusted.loadURL("data:text/html,<title>untrusted</title>");
  await fetchFrom(untrusted, mode + ":untrusted-window");
  await fetchFrom(untrusted, mode + ":untrusted-spoofed", { "X-Workbench-Local-Token": "spoofed-token" });
  console.log("fixture step", boundaryMode, mode, "untrusted fetches");

  const requestMetadata = { url: backendOrigin + "/capture", webContentsId: trusted.webContents.id,
    webContents: trusted.webContents, frame: trusted.webContents.mainFrame };
  if (boundaryMode === "fixed") {
    assert.equal(isTrustedBackendRequest({ ...requestMetadata, frame: undefined }, backendOrigin), false);
  }
  trusted.destroy();
  if (boundaryMode === "fixed") {
    assert.equal(isTrustedBackendRequest(requestMetadata, backendOrigin), false);
  }
  untrusted.destroy();
  for (const window of BrowserWindow.getAllWindows()) {
    if (!window.isDestroyed() && window.webContents.getURL().includes("example.invalid")) {
      window.destroy();
    }
  }
}

async function installMarkdownAndActivateLinks(window, useProtocolRelativeExternal) {
  await window.webContents.executeJavaScript("document.body.innerHTML = " + JSON.stringify(markdownHtml));
  const anchors = await window.webContents.executeJavaScript("Array.from(document.querySelectorAll('a')).map((anchor) => ({ text: anchor.textContent, href: anchor.getAttribute('href'), target: anchor.getAttribute('target') }))");
  blockedLinks[activeMode] = ["relative", "protocol", "file", "custom"].filter((name) => !anchors.some((anchor) => anchor.text === name));
  await window.webContents.executeJavaScript("document.querySelector(" + JSON.stringify("a[href][target='_blank']") + ").click()");
  if (boundaryMode === "fixed") {
    await window.webContents.executeJavaScript("for (const href of ['//example.invalid/protocol-relative','/relative','#fragment','file:///C:/Windows/notepad.exe','vscode://file/test']) { const a=document.createElement('a'); a.href=href; a.target='_blank'; document.body.appendChild(a); a.click(); }");
  }
}

async function fetchFrom(window, key, headers = {}) {
  await window.webContents.executeJavaScript("fetch(" + JSON.stringify(backendOrigin + "/capture?case=" + encodeURIComponent(key)) + ", { mode: 'cors', headers: " + JSON.stringify(headers) + " }).catch(() => undefined)");
  await waitFor(() => Object.prototype.hasOwnProperty.call(captures, key), key);
}

async function fetchRedirectForward(window, key) {
  await window.webContents.executeJavaScript("fetch(" + JSON.stringify(backendOrigin + "/redirect-token?case=" + encodeURIComponent(key)) + ", { mode: 'no-cors' }).catch(() => undefined)");
  await waitFor(() => Object.prototype.hasOwnProperty.call(forwardedCaptures, key), key);
}

async function fetchFromIframe(window, key) {
  const target = backendOrigin + "/capture?case=" + encodeURIComponent(key);
  const iframeHtml = "<script>fetch(" + JSON.stringify(target) + ", { mode: 'no-cors' }).catch(() => undefined)</script>";
  await window.webContents.executeJavaScript("new Promise((resolve) => { const frame = document.createElement('iframe'); frame.srcdoc = " + JSON.stringify(iframeHtml) + "; frame.onload = () => resolve(true); document.body.appendChild(frame); })");
  await waitFor(() => Object.prototype.hasOwnProperty.call(captures, key), key);
}

async function navigateFromRenderer(window, url) {
  await new Promise((resolve, reject) => {
    const contents = window.webContents;
    const timeout = setTimeout(() => { cleanup(); reject(new Error("Navigation did not settle")); }, 5000);
    function cleanup() { clearTimeout(timeout); contents.off("will-frame-navigate", navigated); contents.off("did-finish-load", done); }
    function done() { cleanup(); resolve(); }
    function navigated(event) { setImmediate(() => { if (event.defaultPrevented) done(); }); }
    contents.on("will-frame-navigate", navigated);
    contents.once("did-finish-load", done);
    void contents.executeJavaScript("window.location.href = " + JSON.stringify(url)).catch((error) => { cleanup(); reject(error); });
  });
}

function listen(handler) {
  const server = http.createServer(handler);
  return new Promise((resolve, reject) => {
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      resolve({ server, port: address.port });
    });
  });
}

async function waitFor(predicate, label) {
  const expires = Date.now() + 5000;
  while (Date.now() < expires) {
    if (predicate()) {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 25));
  }
  throw new Error("Timed out waiting for " + label);
}
`;
}

function compileMainModule(fileName) {
  const sourcePath = path.join(desktopRoot, "src/main", fileName);
  let source = readFileSync(sourcePath, "utf8");
  source = source.replaceAll('from "./localTrust"', 'from "./localTrust.mjs"');
  source = source.replaceAll('from "./localTrust";', 'from "./localTrust.mjs";');
  const output = ts.transpileModule(source, {
    compilerOptions: {
      target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.ES2022,
      moduleResolution: ts.ModuleResolutionKind.Bundler,
      isolatedModules: true,
      esModuleInterop: true,
      skipLibCheck: true,
    },
    fileName: sourcePath,
  });
  const outPath = path.join(scratch, fileName.replace(/\.ts$/, ".mjs"));
  writeFileSync(outPath, output.outputText, "utf8");
  return outPath;
}
