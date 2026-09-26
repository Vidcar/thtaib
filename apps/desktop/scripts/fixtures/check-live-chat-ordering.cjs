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
  const action = async (name, number, line) => { await js(`window.fixture.action(${JSON.stringify(name)},${number ?? "undefined"},${line ?? "undefined"})`); };
  const latest = (s, label) => assert.ok(s.geometry.height - s.geometry.top - s.geometry.client <= 2, `${label} follows the bottom: ${JSON.stringify(s.geometry)}`);
  const stable = s => { assert.ok(s.feedSame, "feed remains mounted"); assert.ok(s.bubbleSame, "old assistant DOM row remains mounted"); assert.ok(s.toolSame, "old tool disclosure DOM remains mounted"); assert.ok(s.disclosureOpen, "explicit open state survives later turns and metadata"); };
  try {
    await win.loadURL(process.argv[2]);
    await wait("window.fixture?.labels().join('|')==='TURN ONE'", "initial conversation did not hydrate");
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
      await action("startFinal", number); await wait(`window.fixture.labels().includes('FINAL ${number}')`, "streamed final missing");
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
    // Compare exact readable content, excluding the user's intentionally open
    // disclosure. Hydration must change neither row chronology nor results.
    const normalize = text => text.replace(/\s+/g, " ");
    assert.equal(normalize(reopened.readableText), normalize(warm.readableText), "refresh must preserve the same readable transcript");
    fs.writeFileSync(path.join(scratch, "refreshed-output.json"), JSON.stringify(reopened, null, 2));
    console.log("Native mounted ChatPanel actual-SDK ordering, identity, scrolling, selection and refresh checks passed.");
  } catch (error) { console.error(error); try { console.error(JSON.stringify(await snapshot())); const picture=await win.webContents.capturePage();fs.writeFileSync(path.join(scratch,"failure.png"),picture.toPNG()); } catch {} process.exitCode = 1; }
  finally { win.destroy(); app.exit(process.exitCode ?? 0); }
});
