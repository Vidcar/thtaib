const { app, BrowserWindow } = require("electron");
const fs = require("node:fs"), path = require("node:path"), assert = require("node:assert/strict");
const scratch = process.env.WORKBENCH_BROWSER_RAIL_SCRATCH;
app.setPath("userData", path.join(scratch, "electron-profile"));
app.disableHardwareAcceleration();
for (const flag of ["disable-renderer-backgrounding", "disable-background-timer-throttling", "disable-backgrounding-occluded-windows"]) app.commandLine.appendSwitch(flag);
app.whenReady().then(async () => {
  const win = new BrowserWindow({ width: 1040, height: 850, useContentSize: true, show: false, webPreferences: { offscreen: true, sandbox: true, contextIsolation: true, nodeIntegration: false, backgroundThrottling: false } });
  const js = source => win.webContents.executeJavaScript(source);
  const wait = expression => js(`new Promise((resolve,reject)=>{const start=performance.now();function check(){try{if(${expression})return resolve()}catch{}if(performance.now()-start>6000)return reject(Error(${JSON.stringify(expression)}));requestAnimationFrame(check)}check()})`);
  const button = label => `Array.from(document.querySelectorAll('button')).find(button=>button.textContent.trim()===${JSON.stringify(label)})`;
  const centre = () => js(`(()=>{const r=document.querySelector('.browser-viewport').getBoundingClientRect();return {x:Math.round(r.left+r.width/2),y:Math.round(r.top+r.height/2)}})()`);
  const click = async () => { const position = await centre(); win.webContents.sendInputEvent({ type: "mouseDown", button: "left", clickCount: 1, ...position }); win.webContents.sendInputEvent({ type: "mouseUp", button: "left", clickCount: 1, ...position }); };
  try {
    await win.loadURL(process.argv[2]);
    await wait(`document.querySelector('.browser-viewport img')?.complete`);
    assert.equal(await js(`!!document.querySelector('iframe,webview')`), false, "websites never execute inside the trusted renderer");
    await js(`${button("Take control")}.click()`);
    await wait(`document.querySelector('.browser-viewport').getAttribute('aria-disabled')==='false'`);
    await click();
    await js(`(()=>{const data=new DataTransfer();data.setData('text/plain','native fixture paste');document.activeElement.dispatchEvent(new ClipboardEvent('paste',{bubbles:true,clipboardData:data}))})()`);
    await wait(`window.fixture.calls.some(call=>call.body?.action?.type==='text' && call.body.action.text==='native fixture paste')`);
    for (const width of [1040, 600, 360]) {
      win.setContentSize(width, 850); await wait(`innerWidth===${width}`);
      await js(`new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))`);
      const geometry = await js(`(()=>{const rail=document.querySelector('.chat-rail'),r=rail.getBoundingClientRect(),v=document.querySelector('.browser-viewport').getBoundingClientRect();return {width:innerWidth,scroll:document.documentElement.scrollWidth,rail:{left:r.left,right:r.right,width:r.width,scroll:rail.scrollWidth},view:{width:v.width,height:v.height},resolution:document.querySelector('.browser-resolution small').textContent}})()`);
      assert.ok(geometry.scroll <= width + 1 && geometry.rail.right <= width + 1 && geometry.rail.scroll <= geometry.rail.width + 1, `Browser stays inside ${width}px window: ${JSON.stringify(geometry)}`);
      assert.ok(geometry.view.height >= 450, "the live page uses available rail height");
      assert.match(geometry.resolution, /1440 × 900/, "resizing the rail does not resize the browser viewport");
      const baseline = await js(`window.fixture.calls.length`);
      await click(); await wait(`window.fixture.calls.slice(${baseline}).some(call=>call.body?.action?.event==='up')`);
      const action = await js(`window.fixture.calls.slice(${baseline}).find(call=>call.body?.action?.event==='down').body.action`);
      assert.ok(Math.abs(action.x - 720) < 8 && Math.abs(action.y - 450) < 8, "decoded native image maps centre clicks to actual desktop pixels");
      fs.writeFileSync(path.join(scratch, `browser-rail-${width}.png`), (await win.webContents.capturePage()).toPNG());
    }
    win.setContentSize(1040, 850); await wait(`innerWidth===1040`);
    await js(`(()=>{const select=document.querySelector('[aria-label="Browser resolution"]');select.value='phone';select.dispatchEvent(new Event('change',{bubbles:true}))})()`);
    await wait(`document.querySelector('.browser-resolution small').textContent.includes('390 × 844') && document.querySelector('.browser-viewport img')?.complete && document.querySelector('.browser-viewport').getAttribute('aria-disabled')==='false'`);
    const baseline = await js(`window.fixture.calls.length`);
    await click(); await wait(`window.fixture.calls.slice(${baseline}).some(call=>call.body?.action?.event==='up')`);
    const portrait = await js(`window.fixture.calls.slice(${baseline}).find(call=>call.body?.action?.event==='down').body.action`);
    assert.ok(Math.abs(portrait.x - 195) < 2 && Math.abs(portrait.y - 422) < 2, "phone letterbox maps correctly in actual Electron DOM");
    await js(`window.fixture.toggle(false)`); await wait(`window.fixture.streams===0`);
    assert.equal(await js(`window.fixture.calls.some(call=>call.method==='DELETE')`), false, "native rail dismissal leaves Chrome owned by the chat");
    await js(`window.fixture.toggle(true)`); await wait(`window.fixture.streams===1 && document.querySelector('.browser-viewport img')?.complete`);
    assert.match(await js(`document.querySelector('.browser-resolution small').textContent`), /390 × 844/, "reopening keeps the same viewport");
    await js(`window.fixture.switchChat('two')`); await wait(`window.fixture.aborted>=2 && document.querySelector('.browser-resolution small').textContent.includes('1440 × 900')`);
    assert.equal(await js(`window.fixture.streams`), 1, "chat switching has only one live stream");
    console.log("Browser rail native Electron frame decoding, responsive bounds and scaled input checks passed.");
    win.destroy(); app.exit(0);
  } catch (error) { console.error(error); if (!win.isDestroyed()) win.destroy(); app.exit(1); }
});
