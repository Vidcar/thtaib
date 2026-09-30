const { app, BrowserWindow } = require("electron");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const scratch = process.env.WORKBENCH_LAB_LAYOUT_SCRATCH;
app.setPath("userData", path.join(scratch, "profile"));
let window;
async function waitFor(expression) {
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    if (await window.webContents.executeJavaScript(`Boolean(${expression})`)) return;
    await new Promise(resolve => setTimeout(resolve, 25));
  }
  throw new Error(`Lab layout condition timed out: ${expression}\n${await window.webContents.executeJavaScript("document.body.innerText.slice(0, 2000)")}`);
}
async function geometry() {
  return window.webContents.executeJavaScript(`(() => {
    const visible = element => element.getClientRects().length && getComputedStyle(element).visibility !== 'hidden';
    const labels = [...document.querySelectorAll('.lab-run-controls .setting-row-title')].filter(visible).map(element => {
      const label = element.querySelector('label,.setting-row-name');
      const rect = label.getBoundingClientRect();
      const range = document.createRange(); range.selectNodeContents(label);
      const lines = [...range.getClientRects()];
      const row = element.closest('.setting-row').getBoundingClientRect();
      const control = element.closest('.setting-row').querySelector('.setting-row-control').getBoundingClientRect();
      return { text: label.textContent, width: rect.width, height: rect.height, lines: lines.length, rowWidth: row.width, controlWidth: control.width, withinRow: control.right <= row.right + 1 };
    });
    return { labels, overflow: document.documentElement.scrollWidth > innerWidth + 1 };
  })()`);
}
app.whenReady().then(async () => {
  try {
    window = new BrowserWindow({ width: 1440, height: 1000, show: false, webPreferences: { contextIsolation: true, sandbox: true, nodeIntegration: false } });
    await window.loadURL(process.argv[2]);
    await waitFor(`document.querySelector('[aria-label="Lab model"] option[value="model"]')`);
    const reports = [];
    for (const [width, zoom] of [[1440, 1], [800, 1], [1440, 1.25], [800, 1.25]]) {
      window.setSize(width, 1000); window.webContents.setZoomFactor(zoom);
      await window.webContents.executeJavaScript(`new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))`);
      let report = await geometry();
      for (const label of report.labels) assert.ok(label.lines <= 3 && label.width >= Math.min(70, label.text.replace(/\s/g, "").length * 4), `${width}px/${zoom}: ${label.text} must remain readable: ${JSON.stringify(label)}`);
      await window.webContents.executeJavaScript(`(() => { const select = document.querySelector('[aria-label="Lab model"]'); if(select.value !== 'model') { Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set.call(select,'model'); select.dispatchEvent(new Event('change',{bubbles:true})); } })()`);
      await waitFor(`document.querySelector('[aria-label="Context"]')`);
      await window.webContents.executeJavaScript(`document.querySelector('[aria-label="Performance mode"] input[value="concurrent"]').click()`);
      await waitFor(`document.querySelector('[aria-label="Concurrent requests"]')`);
      await window.webContents.executeJavaScript(`document.querySelector('.lab-load-controls details').open=true`);
      await window.webContents.executeJavaScript(`new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))`);
      report = await geometry();
      assert.equal(report.overflow, false, `${width}px/${zoom}: Lab must not overflow horizontally`);
      for (const label of report.labels) {
        assert.ok(label.lines <= 3 && label.width >= Math.min(70, label.text.replace(/\s/g, "").length * 4), `${width}px/${zoom}: ${label.text} must remain readable: ${JSON.stringify(label)}`);
        assert.ok(label.withinRow, `${label.text}: control must fit its row`);
      }
      reports.push({ width, zoom, ...report });
      fs.writeFileSync(path.join(scratch, `lab-${width}-${zoom}.png`), (await window.webContents.capturePage()).toPNG());
    }
    fs.writeFileSync(path.join(scratch, "geometry.json"), JSON.stringify(reports, null, 2));
    console.log("Native Lab label/control geometry passed at full/narrow widths and 100%/125% zoom.");
    app.exit(0);
  } catch (error) { console.error(error); app.exit(1); }
});
