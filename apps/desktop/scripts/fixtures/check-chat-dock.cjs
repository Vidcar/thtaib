const { app, BrowserWindow } = require("electron");
const path = require("node:path"), assert = require("node:assert/strict");
const scratch = process.env.WORKBENCH_BROWSER_RAIL_SCRATCH;
app.setPath("userData", path.join(scratch, "dock-electron-profile"));
app.disableHardwareAcceleration();
app.commandLine.appendSwitch("disable-renderer-backgrounding");
app.whenReady().then(async () => {
  const win = new BrowserWindow({ width: 1400, height: 850, useContentSize: true, show: false, webPreferences: { offscreen: true, sandbox: true, contextIsolation: true, nodeIntegration: false, backgroundThrottling: false } });
  const js = source => win.webContents.executeJavaScript(source);
  const wait = expression => js(`new Promise((resolve,reject)=>{const start=performance.now();function check(){try{if(${expression})return resolve()}catch{}if(performance.now()-start>8000)return reject(Error(${JSON.stringify(expression)}));requestAnimationFrame(check)}check()})`);
  const button = text => `Array.from(document.querySelectorAll('button')).find(node=>node.textContent.trim()===${JSON.stringify(text)})`;
  const geometry = () => js(`(()=>{const rail=document.querySelector('.chat-rail'),r=rail.getBoundingClientRect(),handle=rail.querySelector('[role=separator]');return {width:r.width,conversation:document.querySelector('.chat-conversation').getBoundingClientRect().width,handle:Number(handle.getAttribute('aria-valuenow')),preferred:window.fixture.preferred,scroll:document.documentElement.scrollWidth}})()`);
  const page = async name => { await js(`${button(name)}.click()`); await wait(`window.fixture.view.page===${JSON.stringify(name.toLowerCase())}`); };
  const input = async (label, value) => js(`(()=>{const node=document.querySelector(${JSON.stringify(`[aria-label="${label}"]`)});Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(node,${JSON.stringify(value)});node.dispatchEvent(new Event('input',{bubbles:true}))})()`);
  const tree = `document.querySelector('[aria-label="Project file tree"] > div')`;
  const editorReady = async file => {
    await wait(`document.querySelector('.chat-dock-editor')?.dataset.path===${JSON.stringify(file)} && window.fixture.editor()?.getModel()?.getLineCount()===400`);
    await js(`new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))`);
  };
  const fileRow = file => `Array.from(document.querySelectorAll('.project-file-row button')).find(node=>node.textContent.includes(${JSON.stringify(file)}))`;
  const scrollEditor = async (line, top) => { await js(`window.fixture.editor().setPosition({lineNumber:${line},column:8});window.fixture.editor().setScrollTop(${top})`); await wait(`window.fixture.editor()?.getScrollTop()===${top}`); };
  const innerReadingRestored = () => wait(`${tree}?.scrollTop===560 && window.fixture.editor()?.getScrollTop()===1200 && window.fixture.editor()?.getPosition().lineNumber===120`);
  const reload = async () => { const done = new Promise(resolve => win.webContents.once("did-finish-load", resolve)); win.reload(); await done; };
  try {
    await win.loadURL(process.argv[2]); await wait(`window.fixture && document.querySelector('[aria-label="Toggle dock"]')`);
    await js(`localStorage.clear();localStorage.setItem('workbench.inspector.width','420')`); await reload(); await wait(`window.fixture?.preferred===420`);
    await js(`document.querySelector('[aria-label="Toggle dock"]').click()`); await wait(`!document.querySelector('.chat-rail').hidden && document.querySelector('.retained-file-name')`);
    const baseline = await geometry(); assert.ok(Math.abs(baseline.width - 420) < 1); assert.equal(baseline.handle, 420);
    for (const name of ["Files", "Helpers", "Browser"]) {
      await page(name); const current = await geometry(); assert.equal(current.width, baseline.width, `${name} keeps one width`); assert.equal(current.handle, Math.round(current.width));
      await js(`document.querySelector('[role=separator]').dispatchEvent(new MouseEvent('dblclick',{bubbles:true}))`); await wait(`window.fixture.preferred===320`);
      assert.ok(Math.abs((await geometry()).width - 320) < 1, `${name} has the same reset`);
      await js(`document.querySelector('[role=separator]').dispatchEvent(new KeyboardEvent('keydown',{key:'End',bubbles:true}))`); await wait(`window.fixture.preferred===672`);
      await js(`document.querySelector('[role=separator]').dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true}))`); await wait(`window.fixture.preferred===656`);
      await js(`document.querySelector('[role=separator]').dispatchEvent(new MouseEvent('dblclick',{bubbles:true}))`); await wait(`window.fixture.preferred===320`);
      // Restore the common baseline for the next page.
      for (let index = 0; index < 6; index++) await js(`document.querySelector('[role=separator]').dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowLeft',bubbles:true}))`);
      await wait(`window.fixture.preferred===416`);
      await js(`document.querySelector('[role=separator]').dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowLeft',bubbles:true}))`); await wait(`window.fixture.preferred===432`);
      baseline.width = (await geometry()).width;
    }
    await wait(`window.fixture.streams===1`); await page("Files"); await wait(`window.fixture.streams===0`);
    await js(`Array.from(document.querySelectorAll('.project-file-row button')).find(node=>node.textContent.includes('src')).click()`); await wait(`window.fixture.view.folders.includes('src')`);
    await wait(`Array.from(document.querySelectorAll('.project-file-row button')).some(node=>node.textContent.includes('file.txt'))`);
    await js(`Array.from(document.querySelectorAll('.project-file-row button')).find(node=>node.textContent.includes('file.txt')).click()`); await wait(`window.fixture.view.path==='src/file.txt'`);
    await editorReady("src/file.txt"); await scrollEditor(120, 1200);
    await js(`${fileRow("README.md")}.click()`); await editorReady("README.md"); await scrollEditor(30, 240);
    await js(`${fileRow("file.txt")}.click()`); await editorReady("src/file.txt"); await wait(`window.fixture.editor()?.getScrollTop()===1200 && window.fixture.editor()?.getPosition().lineNumber===120`);
    await input("Filter project files", "file");
    await js(`${tree}.scrollTop=560;${tree}.dispatchEvent(new Event('scroll',{bubbles:true}))`); await wait(`window.fixture.view.treeScroll===560`);
    await js(`document.querySelector('.retained-file-name').click()`); await wait(`window.fixture.view.previewId==='asset_0' && document.querySelector('.chat-retained-preview')`);
    await js(`(()=>{const body=document.querySelector('.chat-rail-body');body.dispatchEvent(new WheelEvent('wheel',{bubbles:true}));body.scrollTop=350;body.dispatchEvent(new Event('scroll',{bubbles:true}))})()`); await wait(`window.fixture.view.filesScroll===350`);
    await page("Helpers"); await js(`${button("Research helper")}.click()`); await wait(`window.fixture.view.helper==='selected'`);
    await js(`(()=>{const body=document.querySelector('.chat-rail-body');body.dispatchEvent(new WheelEvent('wheel',{bubbles:true}));body.scrollTop=200;body.dispatchEvent(new Event('scroll',{bubbles:true}))})()`); await wait(`window.fixture.view.helpersScroll===200`);
    await page("Files"); await wait(`document.querySelector('.chat-retained-preview') && document.querySelector('.chat-rail-body').scrollTop===350`);
    await editorReady("src/file.txt"); await innerReadingRestored();
    assert.equal(await js(`document.querySelector('[aria-label="Filter project files"]').value`), "file");
    await js(`document.querySelector('[aria-label="Toggle dock"]').click()`); await wait(`document.querySelector('.chat-rail').hidden`);
    await js(`document.querySelector('[aria-label="Toggle dock"]').click()`); await wait(`document.querySelector('.chat-rail-body').scrollTop===350`);
    await page("Helpers"); await wait(`document.querySelector('.chat-rail-body').scrollTop===200 && ${button("All helpers")}`);
    await js(`window.fixture.selectChat('two')`); await wait(`document.querySelector('.chat-rail').hidden && window.fixture.view.filter===''`);
    await js(`document.querySelector('[aria-label="Toggle dock"]').click()`); await wait(`!document.querySelector('.chat-rail').hidden && ${fileRow("README.md")}`);
    await js(`${fileRow("README.md")}.click()`); await editorReady("README.md"); await scrollEditor(15, 160);
    await js(`window.fixture.selectChat('one')`); await wait(`!document.querySelector('.chat-rail').hidden && window.fixture.view.helper==='selected'`);
    await page("Files"); await editorReady("src/file.txt"); await innerReadingRestored();
    assert.equal(await js(`window.fixture.view.fileViews['project:README.md'].scrollTop`), 240, "each path keeps its own editor view in this chat");
    assert.equal(await js(`JSON.parse(localStorage.getItem('workbench.chat.dock.view:two')).fileViews['project:README.md'].scrollTop`), 160, "another chat has its own view of the same file");
    await page("Helpers");
    const preferred = await js(`window.fixture.preferred`);
    for (const [available, rendered] of [[720, 320], [706, 306], [680, 280]]) {
      win.setContentSize(available, 850); await wait(`innerWidth===${available} && Number(document.querySelector('[role=separator]').getAttribute('aria-valuenow'))===${rendered}`);
      for (const name of ["Files", "Helpers", "Browser"]) {
        await page(name); const narrow = await geometry(); assert.equal(narrow.preferred, preferred); assert.ok(Math.abs(narrow.width - rendered) < 1); assert.ok(narrow.conversation >= 400, `${name} retains readable conversation width`); assert.ok(narrow.scroll <= available + 1);
      }
    }
    win.setContentSize(679, 850); await wait(`innerWidth===679 && document.querySelector('.chat-rail').hidden`); assert.equal(await js(`window.fixture.preferred`), preferred);
    win.setContentSize(1400, 850); await wait(`innerWidth===1400 && !document.querySelector('.chat-rail').hidden`); assert.ok(Math.abs((await geometry()).width - preferred) < 1);
    await page("Browser"); await wait(`window.fixture.streams===1`); await js(`document.querySelector('[aria-label="Toggle dock"]').click()`); await wait(`window.fixture.streams===0`);
    await reload(); await wait(`window.fixture?.view.page==='browser' && window.fixture.view.helper==='selected' && window.fixture.preferred===${preferred}`);
    await page("Files"); await editorReady("src/file.txt"); await innerReadingRestored();
    console.log("Chat dock native shared geometry, resize/reset, tree/editor view retention, scoped Files and hidden Browser checks passed.");
    win.destroy(); app.exit(0);
  } catch (error) { console.error(error); console.error(await js(`(()=>{const editor=window.fixture?.editor();return {view:window.fixture?.view,editor:editor?{top:editor.getScrollTop(),lines:editor.getModel()?.getLineCount(),position:editor.getPosition(),layout:editor.getLayoutInfo()}:null,path:document.querySelector('.chat-dock-editor')?.dataset.path}})()`)); if (!win.isDestroyed()) win.destroy(); app.exit(1); }
});
