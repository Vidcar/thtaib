/* Owned Chrome context shared by the official MCP server and a typed private rail API. */
'use strict';

const crypto = require('node:crypto');
const fs = require('node:fs/promises');
const http = require('node:http');
const path = require('node:path');
const { chromium } = require('playwright');
const { createConnection } = require('@playwright/mcp');
const { StdioServerTransport } = require('@modelcontextprotocol/sdk/server/stdio.js');

const token = process.env.WORKBENCH_BROWSER_TOKEN;
const profileDir = process.env.WORKBENCH_BROWSER_PROFILE;
const outputDir = process.env.WORKBENCH_BROWSER_OUTPUT;
const manifestPath = process.env.WORKBENCH_BROWSER_MANIFEST;
if (!token || !profileDir || !outputDir || !manifestPath)
  throw new Error('The browser worker must be started by its backend owner.');

const sessionId = crypto.randomUUID();
let context, starting, closing = false, lost = false, revision = 0, frameSeq = 0;
let activePage, latestFrame, streaming = false, recordingPage;
let streamUpdate = Promise.resolve(), mutation = Promise.resolve();
let inputReset = Promise.resolve();
let viewport = { width: 1440, height: 900 };
let attribution = null;
let authorized = false, authorize;
const ownershipReady = new Promise(resolve => { authorize = resolve; });
const records = new Map();
const downloads = new Map();
const downloadTasks = new Set();
const activeDownloads = new Map();
const pendingPageOperations = new Set();
const MAX_DOWNLOAD = 50 * 1024 * 1024;

function fail(message, code = 'browser_action_invalid', status = 422) {
  const error = new Error(message);
  error.code = code;
  error.status = status;
  throw error;
}
function bump() { revision++; latestFrame = undefined; }
function pages() { return context ? context.pages().filter(page => !page.isClosed()) : []; }
function record(page) { return records.get(page); }
function active() {
  if (activePage && !activePage.isClosed()) return activePage;
  activePage = pages()[0];
  return activePage;
}
function byId(id) { return pages().find(page => record(page)?.page_id === id); }
function setActive(page) {
  if (activePage !== page) { resetInput(activePage); activePage = page; bump(); updateStream(); }
}
function resetInput(onlyPage) {
  inputReset = inputReset.catch(() => {}).then(async () => {
    for (const page of onlyPage ? [onlyPage] : pages()) {
      const info = record(page);
      for (const button of [...(info?.heldButtons || [])]) {
        try { await page.mouse.up({ button }); } catch {}
        info.heldButtons.delete(button);
      }
    }
  });
  return inputReset;
}
function updateStream() {
  streamUpdate = streamUpdate.catch(() => {}).then(async () => {
    const nextPage = streaming ? active() : undefined;
    if (recordingPage === nextPage) return;
    if (recordingPage) await recordingPage.screencast.stop().catch(() => {});
    recordingPage = undefined;
    latestFrame = undefined;
    if (!nextPage || closing || nextPage.isClosed()) return;
    await record(nextPage).viewportReady;
    const recordedRevision = revision;
    await nextPage.screencast.start({
      quality: 75, size: { width: 1280, height: 960 }, fps: 10,
      onFrame: frame => {
        if (!streaming || closing || activePage !== nextPage || nextPage.isClosed()) return;
        // Navigation/resizing advances the epoch; the next stream is started
        // against that epoch so frames already in flight are discarded.
        if (revision !== recordedRevision) return;
        latestFrame = {
          seq: ++frameSeq, session_id: sessionId, page_id: record(nextPage).page_id,
          revision, viewport: { width: frame.viewportWidth, height: frame.viewportHeight },
          timestamp: frame.timestamp, mime_type: 'image/jpeg', data: frame.data.toString('base64'),
        };
      },
    });
    recordingPage = nextPage;
  });
  return streamUpdate;
}
function restartStream() {
  // Force stop/start so no pending frame can carry a previous navigation epoch.
  const old = recordingPage;
  recordingPage = undefined;
  streamUpdate = streamUpdate.catch(() => {}).then(async () => {
    if (old) await old.screencast.stop().catch(() => {});
  });
  return updateStream();
}
function observePage(page) {
  if (records.has(page)) return;
  const actual = page.viewportSize();
  const viewportReady = actual && (actual.width !== viewport.width || actual.height !== viewport.height)
    ? page.setViewportSize(viewport).catch(() => {}) : Promise.resolve();
  const info = { page_id: crypto.randomUUID(), title: '', dialog: null, chooser: null, heldButtons: new Set(), viewportReady };
  records.set(page, info);
  // Keep the public Mouse API on the shared Page; record only held buttons,
  // never coordinates or keystrokes. This also observes upstream mouse tools.
  const down = page.mouse.down.bind(page.mouse), up = page.mouse.up.bind(page.mouse);
  page.mouse.down = async (options = {}) => { await down(options); info.heldButtons.add(options.button || 'left'); };
  page.mouse.up = async (options = {}) => { try { await up(options); } finally { info.heldButtons.delete(options.button || 'left'); } };
  page.on('framenavigated', frame => {
    if (frame !== page.mainFrame()) return;
    resetInput(page); bump(); restartStream();
  });
  page.on('close', () => { records.delete(page); if (activePage === page) activePage = undefined; bump(); restartStream(); });
  page.on('dialog', dialog => {
    const info = record(page);
    info.dialog = dialog;
    bump(); restartStream();
  });
  page.on('filechooser', chooser => {
    record(page).chooser = chooser;
    bump(); restartStream();
  });
  page.on('download', download => {
    const sourceAttribution = attribution && { ...attribution };
    const task = retainDownload(download, sourceAttribution).finally(() => downloadTasks.delete(task));
    downloadTasks.add(task);
  });
  bump();
  setActive(page);
}
async function retainDownload(download, sourceAttribution) {
  const downloadId = crypto.randomUUID();
  activeDownloads.set(downloadId, download);
  const filename = path.basename(download.suggestedFilename()).replace(/[<>:"/\\|?*\x00-\x1f]/g, '_').slice(0, 220) || 'download';
  const destination = path.join(outputDir, 'downloads', downloadId);
  try {
    // Playwright only exposes a completed download path. Streaming HTTP bodies
    // are owned by Chrome; the observer cancels as soon as the staging file is
    // seen over the retention limit, then validates again before publishing.
    await fs.mkdir(path.dirname(destination), { recursive: true });
    const save = download.saveAs(destination);
    let exceeded = false;
    const check = setInterval(async () => {
      const names = await fs.readdir(path.join(outputDir, 'chrome-downloads')).catch(() => []);
      const staged = await Promise.all(names.map(name => fs.stat(path.join(outputDir, 'chrome-downloads', name)).catch(() => null)));
      const stat = await fs.stat(destination).catch(() => null);
      if ((stat && stat.size > MAX_DOWNLOAD) || staged.some(item => item && item.size > MAX_DOWNLOAD)) {
        exceeded = true; await download.cancel().catch(() => {});
      }
    }, 100);
    check.unref();
    try { await save; } finally { clearInterval(check); }
    const stat = await fs.stat(destination);
    if (exceeded || stat.size > MAX_DOWNLOAD) { await fs.rm(destination, { force: true }); throw new Error('Download exceeds the 50 MB browser retention limit.'); }
    downloads.set(downloadId, { download_id: downloadId, path: destination, filename, url: download.url(), attribution: sourceAttribution });
  } catch (error) {
    await fs.rm(destination, { force: true }).catch(() => {});
    downloads.set(downloadId, { download_id: downloadId, filename, url: download.url(), error: String(error.message || error), attribution: sourceAttribution });
  } finally {
    activeDownloads.delete(downloadId);
  }
}
async function ensureContext() {
  if (!authorized) await ownershipReady;
  if (lost) fail('The browser session was lost; reset it before starting fresh pages.', 'browser_session_lost', 409);
  if (closing) fail('The browser is closing.', 'browser_session_closed', 409);
  if (context) return context;
  if (!starting) starting = (async () => {
    await fs.mkdir(profileDir, { recursive: true });
    const launched = await chromium.launchPersistentContext(profileDir, {
      channel: 'chrome', executablePath: process.env.WORKBENCH_CHROME_PATH || undefined,
      headless: true, chromiumSandbox: true, viewport, acceptDownloads: true,
      downloadsPath: path.join(outputDir, 'chrome-downloads'),
    });
    context = launched;
    context.on('page', page => { try { observePage(page); } catch { /* A page observer must not stop other listeners seeing the page. */ } });
    context.on('close', () => { context = undefined; activePage = undefined; if (!closing) lost = true; bump(); });
    // Keep profile authentication but never restore an unfinished live page.
    // newPage can return a page that was already open; closing that page would
    // leave the shared context with no tab for the first navigation.
    const fresh = await context.newPage();
    for (const page of context.pages()) if (page !== fresh) await page.close().catch(() => {});
    const current = fresh.isClosed() ? await context.newPage() : fresh;
    observePage(current);
    setActive(current);
    return context;
  })().catch(error => { starting = undefined; throw error; });
  return starting;
}
async function state() {
  const current = active();
  const openPages = pages();
  await Promise.all(openPages.map(page => record(page).viewportReady));
  await Promise.all(openPages.map(async page => {
    try {
      const title = await Promise.race([page.title(), new Promise(resolve => setTimeout(() => resolve(null), 250))]);
      if (title !== null && record(page)) record(page).title = title;
    } catch {}
  }));
  const actual = current?.viewportSize();
  if (actual && (actual.width !== viewport.width || actual.height !== viewport.height)) {
    viewport = actual; bump(); restartStream();
  }
  const selected = current && record(current);
  return {
    session_id: context ? sessionId : null, lost,
    revision, active_page_id: selected?.page_id || null, viewport,
    tabs: openPages.map(page => ({ page_id: record(page).page_id, title: record(page).title, url: page.url() })),
    dialog: selected?.dialog ? { type: selected.dialog.type(), message: selected.dialog.message(), default_value: selected.dialog.defaultValue() } : null,
    file_chooser: selected?.chooser ? { multiple: selected.chooser.isMultiple() } : null,
    observed_at: new Date().toISOString(),
  };
}
function validateEpoch(body) {
  const page = active();
  if (!context || body.session_id !== sessionId || body.page_id !== record(page)?.page_id || body.revision !== revision)
    fail('The browser changed. Refresh the live view before interacting.', 'browser_stale_action', 409);
  return page;
}
function allowedUrl(value) {
  if (typeof value !== 'string' || value.length > 8192) fail('Enter an HTTP or HTTPS address.');
  let url; try { url = new URL(value); } catch { fail('Enter an HTTP or HTTPS address.'); }
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password)
    fail('Browser addresses must use HTTP or HTTPS without embedded credentials.');
  return url.href;
}
function integer(value, min, max, label) {
  if (!Number.isInteger(value) || value < min || value > max) fail(`${label} must be between ${min} and ${max}.`);
  return value;
}
async function dispatchInput(page, callback) {
  // CDP input can remain outstanding while page JavaScript displays a dialog
  // or file selector. Let the rail respond to that modal without queuing its
  // response behind the operation that needs the response to finish.
  let signal, interrupted = false;
  const modal = new Promise(resolve => { signal = () => { interrupted = true; resolve(); }; });
  page.once('dialog', signal);
  page.once('filechooser', signal);
  const operation = Promise.resolve().then(callback);
  operation.catch(() => {});
  try {
    await Promise.race([operation, modal]);
    if (interrupted) {
      pendingPageOperations.add(operation);
      operation.finally(() => pendingPageOperations.delete(operation)).catch(() => {});
    }
  } finally {
    page.off('dialog', signal);
    page.off('filechooser', signal);
  }
}
async function action(body) {
  await inputReset;
  const page = validateEpoch(body);
  const command = body.action;
  if (!command || typeof command.type !== 'string') fail('A typed browser action is required.');
  if (command.type !== 'dialog' && record(page)?.dialog)
    fail('Respond to the page dialog before interacting.', 'browser_dialog_pending', 409);
  switch (command.type) {
    case 'navigate': await dispatchInput(page, () => page.goto(allowedUrl(command.url), { waitUntil: 'domcontentloaded', timeout: 30000 })); break;
    case 'back': await dispatchInput(page, () => page.goBack({ waitUntil: 'domcontentloaded', timeout: 30000 })); break;
    case 'forward': await dispatchInput(page, () => page.goForward({ waitUntil: 'domcontentloaded', timeout: 30000 })); break;
    case 'reload': await dispatchInput(page, () => page.reload({ waitUntil: 'domcontentloaded', timeout: 30000 })); break;
    case 'select_tab': {
      const target = byId(command.page_id);
      if (!target) fail('That browser tab has closed.', 'browser_stale_action', 409);
      await target.bringToFront(); setActive(target); break;
    }
    case 'new_tab': {
      const target = await context.newPage(); setActive(target);
      if (command.url) await target.goto(allowedUrl(command.url), { waitUntil: 'domcontentloaded', timeout: 30000 });
      break;
    }
    case 'close_tab': {
      const target = byId(command.page_id);
      if (!target) fail('That browser tab has closed.', 'browser_stale_action', 409);
      if (pages().length === 1) await context.newPage();
      await target.close(); setActive(active()); break;
    }
    case 'resize': {
      await resetInput();
      viewport = { width: integer(command.width, 240, 3840, 'Width'), height: integer(command.height, 240, 2160, 'Height') };
      for (const openPage of pages()) await openPage.setViewportSize(viewport);
      bump(); await restartStream(); break;
    }
    case 'pointer': {
      const actual = page.viewportSize();
      if (!Number.isFinite(command.x) || !Number.isFinite(command.y) || command.x < 0 || command.y < 0 || command.x >= actual.width || command.y >= actual.height)
        fail('Pointer coordinates fall outside the current page viewport.');
      const button = command.button || 'left';
      if (!['left', 'middle', 'right'].includes(button)) fail('Unsupported pointer button.');
      await page.mouse.move(command.x, command.y);
      if (command.event === 'down') await dispatchInput(page, () => page.mouse.down({ button }));
      else if (command.event === 'up') await dispatchInput(page, () => page.mouse.up({ button }));
      else if (command.event === 'click') await dispatchInput(page, () => page.mouse.click(command.x, command.y, { button }));
      else if (command.event === 'wheel') {
        if (![command.delta_x || 0, command.delta_y || 0].every(value => Number.isFinite(value) && Math.abs(value) <= 10000)) fail('Scroll distance is out of bounds.');
        await page.mouse.wheel(command.delta_x || 0, command.delta_y || 0);
      } else if (command.event !== 'move') fail('Unsupported pointer event.');
      break;
    }
    case 'key':
      if (typeof command.key !== 'string' || !command.key || command.key.length > 200) fail('A keyboard key is required.');
      await dispatchInput(page, () => page.keyboard.press(command.key)); break;
    case 'text':
      if (typeof command.text !== 'string' || command.text.length > 100000) fail('Text input exceeds the browser limit.');
      await page.keyboard.insertText(command.text); break;
    case 'dialog': {
      const dialog = record(page).dialog;
      if (!dialog) fail('The page dialog has already closed.', 'browser_stale_action', 409);
      if (command.accept) await dialog.accept(typeof command.prompt_text === 'string' ? command.prompt_text.slice(0, 10000) : undefined);
      else await dialog.dismiss();
      record(page).dialog = null; bump(); await restartStream(); break;
    }
    case 'upload': {
      const chooser = record(page).chooser;
      if (!chooser) fail('Open the page file selector before choosing a file.', 'browser_file_chooser_required', 409);
      if (!Array.isArray(command.paths) || command.paths.length > 20 || !command.paths.every(item => typeof item === 'string')) fail('Invalid browser upload files.');
      await chooser.setFiles(command.paths); record(page).chooser = null; bump(); await restartStream(); break;
    }
    default: fail('Unsupported browser action.');
  }
  return state();
}
function authenticated(request) {
  const supplied = request.headers.authorization || '';
  const expected = `Bearer ${token}`;
  return supplied.length === expected.length && crypto.timingSafeEqual(Buffer.from(supplied), Buffer.from(expected));
}
async function readBody(request) {
  const chunks = []; let bytes = 0;
  for await (const chunk of request) { bytes += chunk.length; if (bytes > 256 * 1024) fail('Browser request is too large.', 'browser_action_invalid', 413); chunks.push(chunk); }
  try { return JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}'); } catch { fail('Invalid browser request.'); }
}
async function closeContext() {
  if (closing) return;
  closing = true; streaming = false;
  await updateStream();
  await Promise.allSettled([...activeDownloads.values()].map(download => download.cancel()));
  await Promise.allSettled(downloadTasks);
  if (context) await context.close();
}
const management = http.createServer(async (request, response) => {
  response.setHeader('Cache-Control', 'no-store');
  response.setHeader('Content-Type', 'application/json');
  if (!authenticated(request)) { response.writeHead(401); response.end('{"error":"Unauthorized"}'); return; }
  if (request.headers.origin) { response.writeHead(403); response.end('{"error":"Browser-origin requests are unavailable"}'); return; }
  try {
    const url = new URL(request.url, 'http://127.0.0.1');
    let result;
    if (request.method === 'GET' && url.pathname === '/state') result = await state();
    else if (request.method === 'GET' && url.pathname === '/poll') {
      const after = Number(url.searchParams.get('after') || 0);
      result = { state: await state(), downloads: [...downloads.values()] };
      if (latestFrame && latestFrame.seq > after) result.frame = latestFrame;
    } else if (request.method === 'POST') {
      const body = await readBody(request);
      mutation = mutation.catch(() => {}).then(async () => {
        switch (url.pathname) {
          case '/authorize': authorized = true; authorize(); return { ok: true };
          case '/start': await ensureContext(); return state();
          case '/actions': return action(body);
          case '/validate': validateEpoch(body); return state();
          case '/reset-input': await resetInput(); return state();
          case '/active': {
            const target = pages()[integer(body.index, 0, Math.max(0, pages().length - 1), 'Tab index')];
            if (!target) fail('The browser tab has closed.', 'browser_stale_action', 409);
            setActive(target); return state();
          }
          case '/stream': streaming = body.visible === true; await updateStream(); return state();
          case '/attribution': attribution = body.attribution || null; return { ok: true };
          case '/ack-modal': {
            const info = record(active());
            if (info && body.kind === 'dialog') info.dialog = null;
            else if (info && body.kind === 'file_chooser') info.chooser = null;
            await resetInput(active());
            bump(); await restartStream(); return state();
          }
          case '/ack-download': {
            const item = downloads.get(body.download_id);
            if (item?.path) await fs.rm(item.path, { force: true });
            downloads.delete(body.download_id); return { ok: true };
          }
          case '/close': await closeContext(); return { ok: true };
          default: fail('Unknown browser management operation.', 'browser_action_invalid', 404);
        }
      });
      result = await mutation;
    } else fail('Unknown browser management operation.', 'browser_action_invalid', 404);
    response.end(JSON.stringify(result));
  } catch (error) {
    response.writeHead(error.status || 500);
    // API errors are action-local and never echoed to the transcript; no typed
    // user input, credentials or profile content is added to worker logs.
    response.end(JSON.stringify({ error: String(error.message || error), code: error.code || 'browser_worker_failed' }));
  }
});
management.listen(0, '127.0.0.1', async () => {
  const address = management.address();
  await fs.mkdir(path.dirname(manifestPath), { recursive: true });
  await fs.writeFile(manifestPath, JSON.stringify({ port: address.port, pid: process.pid }), { mode: 0o600 });
});

(async () => {
  const server = await createConnection({
    browser: { browserName: 'chromium', launchOptions: { channel: 'chrome', headless: true }, contextOptions: { viewport } },
    capabilities: ['core', 'vision'], webmcp: false, imageResponses: 'omit', outputDir,
  }, ensureContext);
  const transport = new StdioServerTransport();
  server.onclose = async () => {
    await closeContext().catch(() => {});
    management.close();
    await fs.rm(manifestPath, { force: true }).catch(() => {});
    process.exit(0);
  };
  await server.connect(transport);
  process.stdin.on('end', () => server.close().catch(() => process.exit(1)));
})().catch(error => { console.error('Browser worker initialization failed:', error.message); process.exit(1); });

process.on('SIGTERM', async () => { await closeContext().catch(() => {}); process.exit(0); });
