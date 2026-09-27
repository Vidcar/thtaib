const { app, BrowserWindow } = require("electron");
const fs = require("node:fs"), path = require("node:path"), assert = require("node:assert/strict");
const scratch = process.env.WORKBENCH_ORDERING_SCRATCH;
app.setPath("userData", path.join(scratch, "browser-data")); app.disableHardwareAcceleration();
for (const flag of ["disable-renderer-backgrounding", "disable-background-timer-throttling", "disable-backgrounding-occluded-windows"]) app.commandLine.appendSwitch(flag);
app.whenReady().then(async () => {
  const win = new BrowserWindow({ width: 1040, height: 850, show: false, webPreferences: { offscreen: true, sandbox: true, contextIsolation: true, nodeIntegration: false, backgroundThrottling: false } });
  const js = source => win.webContents.executeJavaScript(source);
  const samples = [];
  const expectRows = number => Array.from({ length: number }, (_, i) => [`TURN ${["ONE", "TWO", "THREE"][i]}`, `CHECK ${i + 1}`, `turn-${i + 1}.txt`, `FINAL ${i + 1}`]).flat();
  const wait = async (expression, label) => {
    await js(`new Promise((resolve,reject)=>{const start=performance.now();function check(){try{if(${expression})return resolve()}catch{}if(performance.now()-start>5000)return reject(Error(${JSON.stringify(label)}));requestAnimationFrame(check)}check()})`);
  };
  const snapshot = () => js("window.fixture.snapshot()");
  const usage = () => js("window.fixture.usage()");
  const action = async (name, number, line) => { await js(`window.fixture.action(${JSON.stringify(name)},${number ?? "undefined"},${line ?? "undefined"})`); };
  const latest = (s, label) => assert.ok(s.geometry.height - s.geometry.top - s.geometry.client <= 2, `${label} follows the bottom: ${JSON.stringify(s.geometry)}`);
  const stable = s => { assert.ok(s.feedSame, "feed remains mounted"); assert.ok(s.bubbleSame, "old assistant DOM row remains mounted"); assert.ok(s.toolSame, "old tool disclosure DOM remains mounted"); assert.ok(s.disclosureOpen, "explicit open state survives later turns and metadata"); };
  const key = keyCode => { win.webContents.sendInputEvent({ type: "keyDown", keyCode }); win.webContents.sendInputEvent({ type: "keyUp", keyCode }); };
  const dismissUsage = async () => { key("ESCAPE"); await wait("!window.fixture.usage().tooltip", "Escape did not dismiss usage panel"); };
  const checkUsageLayout = (readout, label) => {
    const tip = readout.tooltip;
    assert.ok(tip, `${label} opens a usage panel`);
    assert.equal(readout.liveStatusCount, 1, `${label} has one composer status`);
    assert.deepEqual(readout.transcriptStates, [], `${label} has no active main-message badges`);
    assert.match(readout.trigger, /^Generating/);
    assert.ok(readout.triggerTextRect.right <= readout.triggerRect.right + 1, `${label} keeps the complete live label inside its trigger`);
    assert.ok(readout.triggerRect.right <= readout.stopRect.left + 1, `${label} keeps activity and speed clear of Stop`);
    assert.deepEqual(tip.rows.map(row => [row.label, row.value]), [
      ["Input total", "265,586"], ["Cached input", "265,506"], ["Newly processed", "80"], ["Output", "1,915"],
      ["Prompt processing", "42.21 s"], ["First output delay", "42.48 s"],
    ], `${label} retains complete labelled counts and separate timings`);
    assert.equal(tip.context, "267,501 / 655,36041%", `${label} retains context total, capacity and percentage`);
    assert.ok(tip.horizontalOverflow <= 1, `${label} has no horizontal overflow: ${tip.horizontalOverflow}`);
    assert.ok(tip.rect.left >= 7 && tip.rect.right <= readout.viewportWidth - 7, `${label} stays inside the narrow viewport`);
    for (const row of tip.rows) {
      assert.equal(row.lines, 1, `${label} keeps ${row.label}'s number on one line`);
      assert.ok(row.valueRect.left >= row.labelRect.right - 1, `${label} separates ${row.label} from its value`);
      assert.ok(row.valueRect.right <= tip.rect.right - 7, `${label} contains ${row.label}'s value`);
      assert.ok(Math.abs(row.valueRect.right - tip.rows[0].valueRect.right) <= 1, `${label} aligns ${row.label}'s value`);
    }
    assert.match(tip.text, /Cached and newly processed tokens are parts of input total\./);
    assert.match(tip.text, /Current generation average/);
    assert.match(tip.text, /51\.3 tok\/s/);
  };
  const checkUsage = async () => {
    // The hidden native test window needs a focused renderer to dispatch real
    // focus events; keep it offscreen so it does not interrupt Dave's app.
    win.webContents.debugger.attach("1.3");
    await win.webContents.debugger.sendCommand("Emulation.setFocusEmulationEnabled", { enabled: true });
    const layouts = [];
    for (const larger of [false, true]) for (const theme of ["dark", "light"]) {
      const label = `${theme}-${larger ? "narrow-large-text" : "wide"}`;
      win.setContentSize(larger ? 420 : 1040, 850);
      await js(`window.fixture.appearance(${JSON.stringify(theme)},${larger})`);
      win.webContents.focus();
      await js("document.activeElement?.blur()");
      win.webContents.sendInputEvent({ type: "mouseMove", x: 1, y: 1 });
      const anchor = (await usage()).triggerRect;
      assert.ok(anchor.left >= 0 && anchor.right <= (larger ? 420 : 1040), `${label} keeps the composer trigger visible`);
      const point = { x: Math.round(anchor.x + anchor.width / 2), y: Math.round(anchor.y + anchor.height / 2) };
      win.webContents.sendInputEvent({ type: "mouseMove", ...point });
      await wait("window.fixture.usage().tooltip && getComputedStyle(document.querySelector('.chat-usage-bubble')).visibility==='visible'", `${label} pointer hover did not open panel`);
      await js("window.fixture.frame()");
      const hovered = { ...(await usage()), viewportWidth: larger ? 420 : 1040 };
      checkUsageLayout(hovered, `${label} pointer hover`); layouts.push({ label, ...hovered });
      const picture = await win.webContents.capturePage(); fs.writeFileSync(path.join(scratch, `usage-${label}.png`), picture.toPNG());
      await dismissUsage();
      win.webContents.sendInputEvent({ type: "mouseMove", x: 1, y: 1 });
      await js("document.querySelector('.compose button[aria-label=\"Main agent\"]').focus();window.fixture.frame()");
      key("Tab");
      await wait("window.fixture.usage().focused && window.fixture.usage().tooltip", `${label} keyboard Tab did not open panel`);
      checkUsageLayout({ ...(await usage()), viewportWidth: larger ? 420 : 1040 }, `${label} keyboard focus`);
      await dismissUsage();
      await js("document.activeElement?.blur()");
      if (!win.webContents.debugger.isAttached()) win.webContents.debugger.attach("1.3");
      await win.webContents.debugger.sendCommand("Emulation.setTouchEmulationEnabled", { enabled: true });
      await win.webContents.debugger.sendCommand("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [point] });
      await win.webContents.debugger.sendCommand("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
      await wait("window.fixture.usage().tooltip", `${label} touch tap did not open panel`);
      checkUsageLayout({ ...(await usage()), viewportWidth: larger ? 420 : 1040 }, `${label} touch tap`);
      await dismissUsage();
      await win.webContents.debugger.sendCommand("Emulation.setTouchEmulationEnabled", { enabled: false });
    }
    assert.notEqual(layouts[0].tooltip.background, layouts[1].tooltip.background, "usage panel follows the dark/light palette");
    fs.writeFileSync(path.join(scratch, "usage-layouts.json"), JSON.stringify(layouts, null, 2));
    await action("readoutHistory");
    await wait("window.fixture.usage().trigger?.startsWith('Generating')", "history did not preserve current generation");
    await js("document.activeElement?.blur();window.fixture.frame()");
    await js("document.querySelector('.chat-usage-trigger').focus()");
    await wait("document.querySelector('.usage-history summary')", "history did not reach live measurements");
    key("Tab");
    await wait("document.activeElement === document.querySelector('.usage-history summary')", "keyboard could not reach call history");
    key("Space");
    await wait("document.querySelector('.usage-history').open", "keyboard did not expand call history");
    key("Tab");
    await wait("document.activeElement === document.querySelector('.usage-history ol')", "keyboard could not reach scrollable call measurements");
    const history = await js(`(()=>{const panel=document.querySelector('.chat-usage-bubble'),list=document.querySelector('.usage-history ol');return {text:list.textContent,overflow:panel.scrollWidth-panel.clientWidth,listOverflow:list.scrollWidth-list.clientWidth,rows:[...list.querySelectorAll('dl > div')].map(row=>{const label=row.querySelector('dt').getBoundingClientRect(),value=row.querySelector('dd').getBoundingClientRect();return {labelRight:label.right,valueLeft:value.left,valueRight:value.right,panelRight:panel.getBoundingClientRect().right}})}})()`);
    assert.match(history.text, /Summary.*Stopped.*Not reported.*Work.*Complete.*6,065.*29.*0.41 s/);
    assert.ok(history.overflow <= 1, "expanded narrow history has no horizontal overflow");
    assert.ok(history.listOverflow <= 1, "narrow call history has no horizontal scrolling");
    for (const row of history.rows) { assert.ok(row.valueLeft >= row.labelRight - 1, "history keeps labels and values separate"); assert.ok(row.valueRight <= row.panelRight - 7, "history retains complete values"); }
    const picture = await win.webContents.capturePage(); fs.writeFileSync(path.join(scratch, "usage-history-narrow.png"), picture.toPNG());
    await dismissUsage();
    win.setContentSize(1040, 850); await js("window.fixture.appearance('dark',false);document.activeElement?.blur()");
    win.webContents.sendInputEvent({ type: "mouseMove", x: 1, y: 1 });
  };
  try {
    await win.loadURL(process.argv[2]);
    await wait("window.fixture?.labels().join('|')==='TURN ONE'", "initial conversation did not hydrate");
    // The production shell reserves its 54px rail at 760px, leaving a 706px
    // Chat pane. This fixture mounts ChatPanel alone, so use that pane width.
    win.setContentSize(706, 850);
    await wait("innerWidth===706 && document.querySelector('.chat-main')?.getBoundingClientRect().width<720", "half-width Chat did not settle");
    await js("document.querySelector('.chat-header .chat-rail-toggle').click()");
    await wait("!document.querySelector('.chat-rail').hidden && document.querySelector('.chat-rail-tabs')", "explicit half-width dock opening stayed hidden");
    const dock = await js(`(()=>{const chat=document.querySelector('.chat-conversation').getBoundingClientRect(),composer=document.querySelector('.compose').getBoundingClientRect(),dock=document.querySelector('.chat-rail').getBoundingClientRect();return {chat:{left:chat.left,right:chat.right,width:chat.width},composer:{left:composer.left,right:composer.right},dock:{left:dock.left,right:dock.right,width:dock.width},pages:[...document.querySelectorAll('.chat-rail-tabs [role="tab"]')].map(node=>node.textContent)}})()`);
    assert.deepEqual(dock.pages,["Files","Browser","Helpers"],"half-width dock keeps the three explicit pages");
    assert.ok(dock.chat.width>=398 && dock.dock.width>=230,`half-width transcript and dock remain usable: ${JSON.stringify(dock)}`);
    assert.ok(dock.chat.right<=dock.dock.left+1 && dock.composer.right<=dock.dock.left+1,`dock does not cover transcript or composer: ${JSON.stringify(dock)}`);
    await js("document.querySelector('.chat-header .chat-rail-toggle').click()");
    await wait("document.querySelector('.chat-rail').hidden", "closing the dock returns the width");
    win.setContentSize(600,850);
    await wait("innerWidth===600 && document.querySelector('.chat-main')?.getBoundingClientRect().width<640 && document.querySelector('.chat-header .chat-rail-toggle')?.title.startsWith('Widen window')", "narrow Chat did not settle");
    await js("document.querySelector('.chat-header .chat-rail-toggle').click()");
    await wait("document.querySelector('.chat-rail').hidden && document.querySelector('.chat-header .chat-rail-toggle').getAttribute('aria-pressed')==='false' && document.body.textContent.includes('Widen this window to open Files')", "unusable narrow dock must stay closed with a correction");
    win.setContentSize(1040,850);
    await wait("innerWidth===1040", "wide Chat restored after dock check");
    for (let number = 1; number <= 3; number++) {
      if (number === 2) {
        const lookupsBefore = (await js("window.fixture.serverState()")).chatGets;
        await action("beginHeld", number);
        await js(`new Promise((resolve,reject)=>{const start=performance.now();async function check(){if((await window.fixture.serverState()).chatGets>${lookupsBefore})return resolve();if(performance.now()-start>5000)return reject(Error('queued admission lookup missing'));requestAnimationFrame(check)}check()})`);
        await wait("window.fixture.snapshot().labels.length===4", "previous rows disappear during queued admission");
        // A full animation frame after the event has been rendered checks the
        // actual warm DOM while the authoritative admission is still withheld.
        await js("window.fixture.frame()");
        const held = await snapshot(); stable(held); assert.deepEqual(held.labels, expectRows(1)); assert.equal(held.tools, 1);
        await action("releaseAdmission");
        await wait("window.fixture.labels().includes('TURN TWO')", "queued turn was not adopted");
        const metadataHeld = await snapshot(); stable(metadataHeld); assert.equal(metadataHeld.tools, 1);
      } else if (number === 3) {
        await action("begin", number); await wait("window.fixture.labels().includes('TURN THREE')", "third turn was not adopted");
      }
      await action("text", number); await wait(`window.fixture.labels().includes('CHECK ${number}')`, "intermediate assistant row missing");
      await action("tool", number); await wait(`window.fixture.snapshot().tools===${number}`, "owned tool count mismatch");
      if (number === 1) {
        await action("readoutTools"); await wait("window.fixture.usage().trigger==='Using tools'", "native composer did not report tools");
        assert.deepEqual((await usage()).transcriptStates, [], "main transcript has no duplicate active badge while tools run");
      }
      await action("startFinal", number); await wait(`window.fixture.labels().includes('FINAL ${number}')`, "streamed final missing");
      if (number === 1) {
        await action("readoutGenerating"); await wait("window.fixture.usage().trigger?.startsWith('Generating')", "activity-only change did not reach the native composer");
        await checkUsage();
      }
      for (let line = 1; line <= 12; line++) {
        await action("appendFinal", number, line);
        await wait(`window.fixture.lastAnswer().includes('Paragraph ${line}.')`, "current answer's native delta did not render");
        await js("window.fixture.frame()");
        const s = await snapshot(); samples.push({ number, line, ...s.geometry }); latest(s, `turn ${number} delta ${line}`);
      }
      if (number === 3) {
        await js("document.querySelector('.transcript').tabIndex=0;document.querySelector('.transcript').focus()"); win.webContents.focus();
        for (let page = 0; page < 2; page++) { win.webContents.sendInputEvent({ type: "keyDown", keyCode: "PAGEUP" }); win.webContents.sendInputEvent({ type: "keyUp", keyCode: "PAGEUP" }); }
        await wait("window.fixture.geometry().height-window.fixture.geometry().top-window.fixture.geometry().client>96", "PageUp did not reach older output");
        await js("new Promise(resolve=>{let previous=-1,stable=0;function check(){const top=window.fixture.geometry().top;stable=top===previous?stable+1:0;previous=top;if(stable>=3)return resolve();requestAnimationFrame(check)}check()})");
        assert.equal(await js("window.fixture.selectOld()"), "TURN ONE"); const before = await snapshot();
        await action("appendFinal", number, 13); await wait("window.fixture.lastAnswer().includes('Paragraph 13.')", "selected reader's latest delta did not render"); await js("window.fixture.frame()"); const reading = await snapshot();
        assert.equal(reading.selection, "TURN ONE", "streaming keeps selected old text"); assert.ok(reading.geometry.height - reading.geometry.top - reading.geometry.client > 96, "new output does not pull the reader to the bottom");
        assert.ok(Math.abs(reading.geometry.top - before.geometry.top) <= 2, "manual reading position stays stable"); assert.ok(reading.geometry.jump, "manual reader has Latest control");
        await js("document.querySelector('[aria-label=\"Jump to latest message\"]').click();window.fixture.frame()"); latest(await snapshot(), "explicit Latest with selection"); await js("window.fixture.clearSelection()");
      }
      await action("settle", number); await js("window.fixture.frame()");
      const s = await snapshot(); assert.deepEqual(s.labels, expectRows(number)); assert.equal(s.tools, number); latest(s, `turn ${number} settled`);
      assert.doesNotMatch((await usage()).trigger, /Generating|Using tools|Working|Starting|Stopping|Saving|Summarizing|Waiting|Preparing/, `settled turn ${number} does not retain a live activity label`);
      if (number === 1) { const remembered = await js("window.fixture.remember()"); stable(remembered); }
      else { stable(s); if (number === 2) { await action("releaseMetadata"); await js("window.fixture.frame()"); stable(await snapshot()); } }
    }
    const warm = await snapshot();
    assert.match(warm.text, /RESULT 1/); assert.match(warm.text, /FAILED 2/); assert.doesNotMatch(warm.text, /RESULT 3|Reading turn-3\.txt/);
    fs.writeFileSync(path.join(scratch, "streaming-samples.json"), JSON.stringify(samples, null, 2));
    fs.writeFileSync(path.join(scratch, "warm-output.json"), JSON.stringify(warm, null, 2));
    const picture = await win.webContents.capturePage(); fs.writeFileSync(path.join(scratch, "warm-output.png"), picture.toPNG());
    await win.loadURL(process.argv[2]); await wait("window.fixture?.labels().length===12", "refreshed snapshot did not hydrate");
    const reopened = await snapshot(); assert.deepEqual(reopened.labels, warm.labels); assert.equal(reopened.tools, warm.tools);
    assert.doesNotMatch((await usage()).trigger, /Generating|Using tools|Working|Starting|Stopping|Saving|Summarizing|Waiting|Preparing/, "reopened completed history does not regain a live label");
    // Compare exact readable content, excluding the user's intentionally open
    // disclosure. Hydration must change neither row chronology nor results.
    const normalize = text => text.replace(/\s+/g, " ");
    assert.equal(normalize(reopened.readableText), normalize(warm.readableText), "refresh must preserve the same readable transcript");
    fs.writeFileSync(path.join(scratch, "refreshed-output.json"), JSON.stringify(reopened, null, 2));
    console.log("Native mounted ChatPanel actual-SDK ordering, identity, scrolling, selection, refresh, single activity status and readable usage hover/focus/touch/Escape checks passed.");
  } catch (error) { console.error(error); try { console.error(JSON.stringify(await snapshot())); console.error(JSON.stringify(await usage())); const picture=await win.webContents.capturePage();fs.writeFileSync(path.join(scratch,"failure.png"),picture.toPNG()); } catch {} process.exitCode = 1; }
  finally { win.destroy(); app.exit(process.exitCode ?? 0); }
});
