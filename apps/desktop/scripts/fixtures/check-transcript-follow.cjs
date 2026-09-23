const { app, BrowserWindow } = require('electron');
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const scratch=process.env.WORKBENCH_FOLLOW_SCRATCH;
app.setPath('userData',path.join(scratch,'browser-data')); app.disableHardwareAcceleration();
app.commandLine.appendSwitch('disable-renderer-backgrounding');
app.commandLine.appendSwitch('disable-background-timer-throttling');
app.commandLine.appendSwitch('disable-backgrounding-occluded-windows');
app.whenReady().then(async()=>{
  const win=new BrowserWindow({width:1000,height:800,show:false,webPreferences:{offscreen:true,sandbox:true,contextIsolation:true,nodeIntegration:false,backgroundThrottling:false}});
  const js=source=>win.webContents.executeJavaScript(source);
  try {
    await win.loadURL(process.argv[2]);
    for(let turn=0;turn<3;turn++) {
      const samples=await js('window.fixture.turn()');
      fs.writeFileSync(path.join(scratch,`turn-${turn}.json`),JSON.stringify(samples,null,2));
      assert.ok(samples.every(s=>s.height-s.top-s.client<=2),`turn ${turn} keeps each streamed paint at latest: ${JSON.stringify(samples.filter(s=>s.height-s.top-s.client>2).slice(0,3))}`);
    }
    const approval=await js(`(()=>{const card=document.createElement('aside');card.style.height='240px';card.textContent='Approval needed';document.querySelector('.transcript').append(card);return window.fixture.frame().then(window.fixture.geometry)})()`);
    assert.ok(approval.height-approval.top-approval.client<=2,`a newly arriving approval stays in view: ${JSON.stringify(approval)}`);
    await js(`document.querySelector('.transcript').focus()`);
    win.webContents.focus();
    win.webContents.sendInputEvent({type:'keyDown',keyCode:'PAGEUP'}); win.webContents.sendInputEvent({type:'keyUp',keyCode:'PAGEUP'});
    await js(`new Promise((resolve,reject)=>{const start=performance.now();function check(){const s=window.fixture.geometry();if(s.height-s.top-s.client>96)return resolve();if(performance.now()-start>2000)return reject(Error('PageUp did not scroll'));requestAnimationFrame(check)}check()})`);
    await js(`new Promise((resolve,reject)=>{let previous=-1,stable=0;const start=performance.now();function check(){const top=window.fixture.geometry().top;stable=top===previous?stable+1:0;previous=top;if(stable>=3)return resolve();if(performance.now()-start>2000)return reject(Error('Scroll did not settle'));requestAnimationFrame(check)}check()})`);
    const before=await js('window.fixture.geometry()');
    assert.ok(before.height-before.top-before.client>96,'native PageUp reads earlier output');
    const after=await js('window.fixture.grow()');
    assert.ok(after.height-after.top-after.client>96,'new output preserves manual reading position');
    assert.ok(after.jump,'manual scrolling shows Latest');
    await js(`document.querySelector('[aria-label="Jump to latest message"]').click();window.fixture.frame()`);
    const final=await js('window.fixture.geometry()');
    assert.ok(final.height-final.top-final.client<=2,`Latest resumes following: ${JSON.stringify({before,after,final})}`);
    console.log('Rendered transcript follow checks passed.');
  } catch(error) { console.error(error); process.exitCode=1; }
  finally { win.destroy(); app.exit(process.exitCode??0); }
});
