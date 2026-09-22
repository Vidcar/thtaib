const { app, BrowserWindow } = require('electron');
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const scratch = process.env.WORKBENCH_VIEWER_SCRATCH;
const userData = path.join(scratch, 'source-reference-browser-data');
fs.mkdirSync(userData, { recursive: true });
app.setPath('userData', userData);
app.disableHardwareAcceleration();
app.whenReady().then(async () => {
  const win = new BrowserWindow({ width: 1280, height: 900, useContentSize: true, show: false, webPreferences: { sandbox: true, contextIsolation: true, nodeIntegration: false, backgroundThrottling: false } });
  const js = source => win.webContents.executeJavaScript(source);
  const ready = predicate => js(`new Promise((resolve,reject)=>{const start=performance.now();function poll(){if(${predicate})return resolve(true);if(performance.now()-start>5000)return reject(Error('Timed out'));requestAnimationFrame(poll)}poll()})`);
  try {
    await win.loadURL(process.argv[2]);
    await ready(`document.querySelectorAll('.source-reference-link').length===2`);
    for (const theme of ['light', 'dark']) for (const width of [1280, 794, 600]) {
      win.setContentSize(width, 900);
      await ready(`Math.abs(innerWidth-${width})<=1`);
      await js(`document.documentElement.dataset.theme='${theme}';document.querySelector('.source-reference-link').focus();document.querySelector('.source-reference-link').click()`);
      await ready(`document.querySelector('dialog[open] pre')`);
      const result = await js(`(()=>{const d=document.querySelector('dialog'),r=d.getBoundingClientRect(),p=d.querySelector('pre');return {width:innerWidth,theme,rect:{left:r.left,right:r.right,top:r.top,bottom:r.bottom},scroll:d.scrollWidth,client:d.clientWidth,preScroll:p.scrollWidth,preClient:p.clientWidth,color:getComputedStyle(d).backgroundColor,focus:document.activeElement?.getAttribute('aria-label'),request:window.fixture.calls.at(-1)}})()`.replace('theme,',`theme:'${theme}',`));
      assert.ok(result.rect.left>=0 && result.rect.right<=result.width+1 && result.rect.bottom<=900, 'source viewer inside viewport');
      assert.ok(result.scroll<=result.client+1 && result.preScroll<=result.preClient+1, 'long passage has no horizontal overflow');
      assert.notEqual(result.color, 'rgba(0, 0, 0, 0)', 'theme gives opaque panel');
      assert.equal(result.request.start_char,12); assert.equal(result.request.end_char,120); assert.equal(result.request.session_id,'chat_fixture');
      assert.equal(result.focus,'Close source','dialog initially focuses dismiss control');
      await js(`new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))`);
      if(width===794) fs.writeFileSync(path.join(scratch, `source-reference-${theme}-794.png`),(await win.webContents.capturePage()).toPNG());
      await js(`document.querySelector('[aria-label="Close source"]').click()`);
      await ready(`!document.querySelector('dialog')`);
      result.closeFocus = await js(`document.activeElement?.textContent`);
      console.log(JSON.stringify(result));
      assert.equal(result.closeFocus,'Read selected passage','closing restores citation focus');
    }
    await js(`document.querySelectorAll('.source-reference-link')[1].focus();document.querySelectorAll('.source-reference-link')[1].click()`);
    await ready(`document.querySelector('dialog [role=alert]')`);
    assert.match(await js(`document.querySelector('[role=alert]').textContent`), /unavailable/);
    assert.equal(await js(`!!document.querySelector('dialog pre')`),false,'failure cannot show a stale passage');
    win.webContents.sendInputEvent({ type:'keyDown', keyCode:'ESC' }); win.webContents.sendInputEvent({ type:'keyUp', keyCode:'ESC' });
    await ready(`!document.querySelector('dialog')`);
    assert.equal(await js(`document.activeElement?.textContent`),'Read missing passage','Escape restores failed citation focus');
    await js(`document.querySelector('.image-preview-button').focus();document.querySelector('.image-preview-button').click()`);
    await ready(`document.querySelector('dialog[open].image-viewer')`);
    await js(`document.querySelector('[aria-label="Close image"]').click()`);
    await ready(`!document.querySelector('dialog')`);
    assert.equal(await js(`document.activeElement?.getAttribute('aria-label')`),'View image Retained image','closing image restores thumbnail focus');
    await js(`document.querySelector('.image-preview-button').click()`);
    await ready(`document.querySelector('dialog[open].image-viewer')`);
    win.webContents.sendInputEvent({ type:'keyDown', keyCode:'ESC' }); win.webContents.sendInputEvent({ type:'keyUp', keyCode:'ESC' });
    await ready(`!document.querySelector('dialog')`);
    assert.equal(await js(`document.activeElement?.getAttribute('aria-label')`),'View image Retained image','Escape restores thumbnail focus');
    await js(`window.fixture.showLibrary()`);
    await ready(`document.querySelector('[aria-label="Preview Library image.png"]')`);
    await js(`document.querySelector('[aria-label="Preview Library image.png"]').click()`);
    await ready(`document.querySelector('[aria-label="View image Library image.png"]')`);
    for (const method of ['escape', 'close']) {
      await js(`document.querySelector('[aria-label="View image Library image.png"]').click()`);
      await ready(`document.querySelector('dialog[open].image-viewer') && window.fixture.resolveOriginal`);
      if (method === 'escape') {
        win.webContents.sendInputEvent({ type:'keyDown', keyCode:'ESC' }); win.webContents.sendInputEvent({ type:'keyUp', keyCode:'ESC' });
      } else await js(`document.querySelector('[aria-label="Close image"]').click()`);
      await ready(`!document.querySelector('dialog')`);
      assert.equal(await js(`document.activeElement?.getAttribute('aria-label')`),'View image Library image.png',`Library ${method} restores retained thumbnail focus`);
      await js(`window.fixture.resolveOriginal();delete window.fixture.resolveOriginal;new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))`);
      assert.equal(await js(`document.activeElement?.getAttribute('aria-label')`),'View image Library image.png','late original completion cannot lose restored Library focus');
    }
    console.log('Source reference native geometry, exact range, failure and keyboard checks passed.');
  } finally { win.destroy(); app.quit(); }
}).catch(error => { console.error(error); app.exit(1); });
