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
  const ready = predicate => js(`new Promise((resolve,reject)=>{const start=performance.now();function poll(){if(${predicate})return resolve(true);if(performance.now()-start>5000)return reject(Error(${JSON.stringify('Timed out: ' + predicate)}));requestAnimationFrame(poll)}poll()})`);
  try {
    await win.loadURL(process.argv[2]);
    win.webContents.setZoomFactor(1);
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
    assert.ok(await js(`document.querySelector('.image-preview-button img').getBoundingClientRect().width<=240`),'Chat image thumbnails keep their compact width');
    await js(`document.querySelector('button[aria-label="Test actions"]').click()`);
    await ready(`document.activeElement?.textContent === 'First action'`);
    win.webContents.sendInputEvent({ type:'keyDown', keyCode:'ESC' }); win.webContents.sendInputEvent({ type:'keyUp', keyCode:'ESC' });
    await ready(`document.querySelector('button[aria-label="Test actions"]').getAttribute('aria-expanded') === 'false'`);
    assert.equal(await js(`document.activeElement?.getAttribute('aria-label')`),'Test actions','Escape restores menu trigger focus');
    await js(`window.fixture.showLibrary()`);
    await ready(`document.querySelector('[aria-label="Preview Library image.png"]')`);
    await js(`document.querySelector('[aria-label="Preview Library image.png"]').click()`);
    await ready(`document.querySelector('[aria-label="View image Library image.png"]')`);
    assert.match(await js(`document.querySelector('.file-preview-pane').textContent`), /Build a simple top-down 2D driving game.*Game project/s, 'Library shows readable chat and project source names');
    assert.equal(await js(`Array.from(document.querySelectorAll('.file-browser button')).some(button=>button.textContent.includes('Use in Chat'))`), false, 'Library has no Chat handoff');
    assert.equal(await js(`!!document.querySelector('.file-selection-bar')`), false, 'Library bulk actions are hidden before selection');
    for (const theme of ['light', 'dark']) for (const width of [1280, 794, 600, 360]) {
      win.setContentSize(width, 900);
      await ready(`Math.abs(innerWidth-${width})<=1`);
      await js(`document.documentElement.dataset.theme='${theme}';new Promise(resolve=>requestAnimationFrame(()=>{document.getAnimations().forEach(animation=>animation.finish());requestAnimationFrame(resolve)}))`);
      const geometry = await js(`(()=>{const panel=document.querySelector('.file-browser'),pane=document.querySelector('.file-preview-pane'),image=pane.querySelector('img'),table=document.querySelector('.file-table-wrap'),name=table.querySelector('.file-name strong'),rect=pane.getBoundingClientRect(),imageRect=image.getBoundingClientRect(),tableRect=table.getBoundingClientRect();return {width:innerWidth,scroll:document.documentElement.scrollWidth,panelScroll:panel.scrollWidth,panelClient:panel.clientWidth,pane:{left:rect.left,right:rect.right,top:rect.top},table:{bottom:tableRect.bottom,nameWidth:name.getBoundingClientRect().width,nameColor:getComputedStyle(name).color},image:{width:imageRect.width,height:imageRect.height},background:getComputedStyle(pane.querySelector('.image-preview-button')).backgroundColor}})()`);
      assert.ok(geometry.scroll<=geometry.width+1 && geometry.panelScroll<=geometry.panelClient+1, `Library has no horizontal overflow at ${width}px in ${theme}`);
      assert.ok(geometry.pane.left>=0 && geometry.pane.right<=geometry.width+1, 'Library detail stays inside the viewport');
      assert.ok(geometry.table.nameWidth>=50, 'Library preserves space for the filename');
      if (width>=600) assert.ok(geometry.image.width>240 && geometry.image.height>150, 'Library images use more space than Chat thumbnails');
      if (width<=600) assert.ok(geometry.pane.top>=geometry.table.bottom-1, 'narrow Library stacks its detail below the table');
      assert.notEqual(geometry.background,'rgba(0, 0, 0, 0)','Library image surface follows the active theme');
      if(width===794) fs.writeFileSync(path.join(scratch, `library-image-${theme}-794.png`),(await win.webContents.capturePage()).toPNG());
      console.log(JSON.stringify({library:true,theme,...geometry}));
    }
    win.setContentSize(794, 900);
    await ready(`Math.abs(innerWidth-794)<=1`);
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
    await js(`document.querySelector('[aria-label="Select Library image.png"]').click()`);
    await ready(`document.querySelector('.file-selection-bar')`);
    await js(`Array.from(document.querySelectorAll('.file-selection-bar button')).find(button=>button.textContent==='Clear selection').click()`);
    await ready(`!document.querySelector('.file-selection-bar')`);
    await js(`(()=>{const select=document.querySelector('[aria-label="File location"]');select.value='project';select.dispatchEvent(new Event('change',{bubbles:true}))})()`);
    await ready(`document.querySelector('select[aria-label="Project"]')`);
    assert.equal(await js(`window.fixture.libraryRequests.at(-1).projectPath`),null,'choosing a scope without a target makes no broad request');
    await js(`(()=>{const select=document.querySelector('select[aria-label="Project"]');select.value='D:/Games';select.dispatchEvent(new Event('change',{bubbles:true}))})()`);
    await ready(`window.fixture.libraryRequests.at(-1).projectPath==='D:/Games'`);
    assert.equal(await js(`window.fixture.libraryRequests.at(-1).sessionId`),null,'Project scope sends one target');
    await js(`(()=>{const select=document.querySelector('[aria-label="File location"]');select.value='chat';select.dispatchEvent(new Event('change',{bubbles:true}))})()`);
    await ready(`document.querySelector('select[aria-label="Chat"]')`);
    await js(`(()=>{const select=document.querySelector('select[aria-label="Chat"]');select.value='sidebar-chat';select.dispatchEvent(new Event('change',{bubbles:true}))})()`);
    await ready(`window.fixture.libraryRequests.at(-1).sessionId==='sidebar-chat'`);
    assert.equal(await js(`window.fixture.libraryRequests.at(-1).projectPath`),null,'Chat scope sends one target');
    await js(`document.documentElement.dataset.theme='light';window.fixture.showToolMenu()`);
    for (const width of [360, 600]) {
      win.setContentSize(width, 750);
      await ready(`Math.abs(innerWidth-${width})<=1 && document.querySelector('button[aria-label="Approval mode"]')`);
      await js(`document.querySelector('button[aria-label="Approval mode"]').click()`);
      await ready(`document.querySelector('.visual-testing-controls')`);
      for (const capability of ['Windows']) {
        await js(`Array.from(document.querySelectorAll('.visual-testing-disclosure')).find(button=>button.textContent.includes('${capability}')).click()`);
        await ready(`Array.from(document.querySelectorAll('.visual-testing-disclosure')).some(button=>button.textContent.includes('${capability}') && button.getAttribute('aria-expanded')==='true')`);
        const geometry = await js(`(()=>{const panel=document.querySelector('.chat-tools-popover-panel'),rect=panel.getBoundingClientRect();return {innerWidth,innerHeight,rect:{left:rect.left,right:rect.right,top:rect.top,bottom:rect.bottom},scrollWidth:panel.scrollWidth,clientWidth:panel.clientWidth,pageScrollWidth:document.documentElement.scrollWidth,active:document.querySelector('.visual-testing-disclosure[aria-expanded="true"]')?.textContent}})()`);
        assert.ok(geometry.rect.left >= 0 && geometry.rect.right <= geometry.innerWidth + 1 && geometry.rect.top >= 0 && geometry.rect.bottom <= geometry.innerHeight + 1, `${capability} menu stays inside ${width}px viewport`);
        assert.ok(geometry.scrollWidth <= geometry.clientWidth + 1 && geometry.pageScrollWidth <= geometry.innerWidth + 1, `${capability} menu has no horizontal overflow at ${width}px`);
        if (width === 360) { await js(`new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))`); fs.writeFileSync(path.join(scratch, `chat-tools-${capability.toLowerCase()}-360.png`), (await win.webContents.capturePage()).toPNG()); }
        console.log(JSON.stringify({ capability, ...geometry }));
      }
      await js(`document.querySelector('button[aria-label="Approval mode"]').click()`);
      await ready(`document.querySelector('button[aria-label="Approval mode"]').getAttribute('aria-expanded')==='false'`);
    }
    console.log('Chat Access native 360px and 600px geometry checks passed.');
    win.setContentSize(1280, 900);
    for (const width of [208, 232, 280]) {
      await js(`window.fixture.showSidebar(${width});window.fixture.chatClicks=0;window.fixture.openedChat=null`);
      await ready(`document.querySelector('.conversation-row .nav-item')`);
      await js(`new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))`);
      const centre = await js(`(()=>{const r=document.querySelector('.conversation-row .nav-item').getBoundingClientRect();return {x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)}})()`);
      win.webContents.sendInputEvent({type:'mouseMove',...centre});
      await ready(`getComputedStyle(document.querySelector('.conversation-actions')).opacity==='1'`);
      const hit = await js(`document.elementFromPoint(${centre.x},${centre.y})?.closest('button')?.className`);
      assert.ok(hit?.includes('nav-item'), `the ${width}px sidebar title's centre remains its own click target while actions are visible`);
      win.webContents.sendInputEvent({type:'mouseDown',button:'left',clickCount:1,...centre});
      win.webContents.sendInputEvent({type:'mouseUp',button:'left',clickCount:1,...centre});
      await ready(`window.fixture.openedChat==='sidebar-chat'`);
      assert.equal(await js(`window.fixture.chatClicks`),1,'one title click opens the chat exactly once');
      const gap = await js(`(()=>{const a=document.querySelector('.conversation-actions').getBoundingClientRect(),b=document.querySelector('.conversation-actions button').getBoundingClientRect();const x=a.left+(b.left-a.left)/2,y=a.top+a.height/2;return {padding:b.left-a.left,hit:document.elementFromPoint(x,y)?.closest('button')?.className}})()`);
      if (gap.padding > 0.5) assert.ok(gap.hit?.includes('nav-item'),'action-group padding passes through to the title');
      const rename = await js(`(()=>{const r=document.querySelector('[aria-label="Rename chat"]').getBoundingClientRect();return {x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)}})()`);
      win.webContents.sendInputEvent({type:'mouseDown',button:'left',clickCount:1,...rename});
      win.webContents.sendInputEvent({type:'mouseUp',button:'left',clickCount:1,...rename});
      await ready(`document.querySelector('.conversation-rename input')`);
      assert.equal(await js(`window.fixture.chatClicks`),1,'the actual Rename button does not open the chat');
      await js(`document.querySelector('.conversation-rename input').dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))`);
      await ready(`document.querySelector('.conversation-row .nav-item')`);
    }
    await js(`Array.from(document.querySelectorAll('.chat-group-toggle')).find(item=>item.textContent.includes('Game project')).click()`);
    await ready(`!document.querySelector('.conversation-row')`);
    await js(`document.querySelector('[aria-label=\"Search chats\"]').click()`);
    await js(`(()=>{const input=document.querySelector('.chat-search input');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,'driving');input.dispatchEvent(new Event('input',{bubbles:true}))})()`);
    await ready(`document.querySelector('.conversation-row') && document.querySelectorAll('.chat-group').length===1`);
    assert.equal(await js(`document.querySelector('.chat-group-toggle').textContent`),'Game project','search retains only the project with a match');
    assert.equal(await js(`!!document.querySelector('.sidebar-loose')`),false,'project search omits an empty No project group');
    assert.doesNotMatch(await js(`document.querySelector('.sidebar-scroll').textContent`),/Unrelated project|No chats yet/,'a matching chat is not buried below empty project headings');
    await js(`(()=>{const input=document.querySelector('.chat-search input');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,'absent');input.dispatchEvent(new Event('input',{bubbles:true}))})()`);
    await ready(`document.querySelector('.sidebar-scroll').textContent.includes('No matching conversations')`);
    assert.equal(await js(`document.querySelectorAll('.chat-group,.sidebar-loose').length`),0,'an empty search renders a single truthful empty state');
    win.setContentSize(600, 900);
    await js(`document.querySelector('[aria-label="Close search"]').click();new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))`);
    assert.equal(await js(`document.querySelector('.destination-rail').getBoundingClientRect().width`),54,'the destination rail keeps its exact width');
    assert.equal(await js(`document.querySelector('.chat-navigation').getBoundingClientRect().width`),0,'narrow layout collapses the secondary list first');
    await js(`document.querySelector('[aria-label="Expand chat list"]').click();new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))`);
    assert.ok(await js(`document.querySelector('.chat-navigation').getBoundingClientRect().width`)>=160,'an explicit choice reopens the existing list at narrow width');
    await js(`document.querySelector('[aria-label="Collapse sidebar"]').click();new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))`);
    assert.equal(await js(`document.querySelector('.chat-navigation').getBoundingClientRect().width`),0,'explicit collapse restores the compact layout');
    for (const width of [600, 760, 794]) {
      win.setContentSize(width, 850);
      await js(`window.fixture.showSidebar(232,'models')`);
      await ready(`document.querySelector('[aria-label="Models"].destination-current')`);
      const geometry = await js(`(()=>{const app=document.querySelector('.app'),rail=document.querySelector('.destination-rail').getBoundingClientRect(),nav=document.querySelector('.workbench-navigation').getBoundingClientRect(),main=document.querySelector('.app > main').getBoundingClientRect(),list=document.querySelector('.chat-navigation').getBoundingClientRect();return {rail:rail.width,nav:nav.width,mainLeft:main.left,mainWidth:main.width,list:list.width,viewport:innerWidth,grid:getComputedStyle(app).gridTemplateColumns}})()`);
      assert.equal(geometry.rail,54,`${width}px Models retains the 54px rail`);
      assert.equal(geometry.nav,54,`${width}px Models reserves no empty Chat list column`);
      assert.equal(geometry.list,0,`${width}px Models hides the Chat-only list`);
      assert.ok(Math.abs(geometry.mainLeft-54)<=1 && geometry.mainWidth>=geometry.viewport-55,`${width}px Models receives the remaining viewport width: ${JSON.stringify(geometry)}`);
    }
    await ready(`document.querySelectorAll('.system-resource-metric[role="meter"]').length===2`);
    // Combine short windows and zoom at usable content heights (at least 360px).
    for (const theme of ['dark', 'light']) for (const [height, zoom] of [[900,1], [500,1], [360,1], [600,1.5], [900,2]]) {
      win.setContentSize(1000, height); win.webContents.setZoomFactor(zoom);
      await js(`document.documentElement.dataset.theme='${theme}';new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))`);
      const geometry = await js(`(()=>{const rect=n=>{const r=n.getBoundingClientRect();return {top:r.top,bottom:r.bottom,width:r.width,height:r.height}};const rail=document.querySelector('.destination-rail'),settings=rail.querySelector('[aria-label="Settings"]'),nav=rail.querySelector('.side-tabs'),s=settings.getBoundingClientRect();return {height:innerHeight,rail:rect(rail),settings:rect(settings),settingsHit:document.elementFromPoint(s.x+s.width/2,s.y+s.height/2)?.closest('button')===settings,dot:rect(rail.querySelector('.status-dot')),nav:{height:nav.clientHeight,scroll:nav.scrollHeight},rings:[...rail.querySelectorAll('.system-resource-ring')].map(n=>({rect:rect(n),text:rect(n.querySelector('.system-resource-percent'))}))}})()`);
      assert.equal(geometry.rail.width,54,'short and scaled windows keep the 54px rail');
      assert.ok(geometry.settings.top>=0 && geometry.settings.bottom<=geometry.height && geometry.settingsHit,`Settings remains reachable: ${JSON.stringify({theme,zoom,height,geometry})}`);
      for (const ring of geometry.rings) {
        assert.equal(ring.rect.width,36); assert.equal(ring.rect.height,36);
        assert.ok(ring.rect.top>=geometry.settings.bottom && ring.rect.bottom<=geometry.height,`rings stay below Settings and inside the viewport: ${JSON.stringify({theme,zoom,height,geometry})}`);
        assert.ok(ring.text.width<=36 && ring.text.height<=36,'percentages fit the rings');
      }
      assert.equal(geometry.rings.length,2); assert.ok(geometry.dot.bottom<=geometry.height,'service dot stays visible');
      if (geometry.nav.scroll>geometry.nav.height) {
        await js(`document.querySelector('.side-tabs').scrollTop=document.querySelector('.side-tabs').scrollHeight`);
        assert.ok(await js(`(()=>{const b=document.querySelector('.side-tabs [aria-label="Lab"]'),r=b.getBoundingClientRect();return document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)?.closest('button')===b})()`),'scrolling keeps the final destination reachable');
      }
    }
    win.webContents.setZoomFactor(1);
    console.log('Sidebar title, action hit targets, resource rings and persistent rail/list native geometry checks passed.');
    win.setContentSize(1280, 900);
    await js(`window.fixture.showFileTree()`);
    const fileButton = name => `Array.from(document.querySelectorAll('.project-file-row button')).find(button=>button.textContent.trim().replace(/^[▸▾]\\s*/, '')===${JSON.stringify(name)})`;
    await ready(fileButton('src'));
    assert.equal(await js(`${fileButton('src')}.getAttribute('aria-expanded')`),'false','an unloaded directory is expandable');
    assert.equal(await js(`${fileButton('blocked.txt')}.getAttribute('aria-expanded')`),null,'files are leaves without a misleading disclosure');
    await js(`${fileButton('blocked.txt')}.click()`);
    await ready(`document.body.textContent.includes('Viewing blocked.txt')`);
    assert.deepEqual(await js(`window.fixture.selectedPaths`),['blocked.txt'],'a single file click opens exactly once through the real tree');
    await js(`${fileButton('src')}.click()`);
    await ready(fileButton('first.txt'));
    assert.equal(await js(`${fileButton('src')}.getAttribute('aria-expanded')`),'true');
    await js(`${fileButton('nested')}.click()`);
    await ready(fileButton('old.txt'));
    await js(`window.fixture.filesAdded=true;window.fixture.refreshFiles()`);
    await ready(`${fileButton('second.txt')} && ${fileButton('new.txt')}`);
    assert.equal(await js(`${fileButton('src')}.getAttribute('aria-expanded')`),'true','write refresh preserves the parent expansion');
    assert.equal(await js(`${fileButton('nested')}.getAttribute('aria-expanded')`),'true','write refresh reloads the expanded descendant');
    await js(`${fileButton('src')}.click()`);
    await ready(`!(${fileButton('first.txt')})`);
    await js(`${fileButton('src')}.click()`);
    await ready(fileButton('new.txt'));
    await js(`window.fixture.holdDirectory=true;window.fixture.holdFile=true;window.fixture.refreshFiles()`);
    await ready(`window.fixture.resolveDirectory && window.fixture.resolveFile`);
    await js(`window.fixture.switchFileProject()`);
    await ready(fileButton('second-only.txt'));
    await js(`${fileButton('second-only.txt')}.click()`);
    await ready(`document.body.textContent.includes('Viewing second-only.txt')`);
    await js(`window.fixture.resolveDirectory();window.fixture.resolveFile();new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))`);
    assert.equal(await js(`!!(${fileButton('late-wrong-project.txt')})`),false,'late directory responses cannot cross project ownership');
    assert.doesNotMatch(await js(`document.body.textContent`),/OLD PROJECT CONTENT|Viewing blocked.txt/,'late file responses cannot replace the new project preview');
    assert.match(await js(`document.body.textContent`),/Viewing second-only.txt/);
    console.log('Project tree native expand, single-click, refresh and ownership checks passed.');
    await js(`window.fixture.showHelperDensity()`);
    await ready(`document.querySelector('.helper-delegation-request')`);
    await js(`new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))`);
    const delegation = await js(`(()=>{const node=document.querySelector('.helper-delegation-request'),style=getComputedStyle(node);return {height:node.getBoundingClientRect().height,lineHeight:parseFloat(style.lineHeight),length:node.textContent.length,clamp:style.webkitLineClamp}})()`);
    assert.equal(delegation.clamp,'2');
    assert.ok(delegation.height <= delegation.lineHeight * 2 + 1,'the full long delegation is visually limited to two lines');
    assert.ok(delegation.length > 2000,'clamping does not remove the exact request text');
    await js(`document.querySelector('.helper-delegation').click()`);
    await ready(`document.querySelector('.helper-request-disclosure')`);
    assert.equal(await js(`document.querySelector('.helper-request-disclosure').open`),false,'full helper request starts collapsed');
    assert.ok(await js(`document.querySelector('[data-helper-activity]').getBoundingClientRect().top < 240`),'helper activity stays visible below the collapsed request');
    await js(`document.querySelector('.helper-request-disclosure summary').click()`);
    await ready(`document.querySelector('.helper-request-disclosure').open`);
    const expandedRequest = await js(`(()=>{const node=document.querySelector('.helper-rail-request');return {length:node.textContent.length,height:node.getBoundingClientRect().height,scroll:node.scrollHeight,client:node.clientHeight}})()`);
    assert.equal(expandedRequest.length,delegation.length,'opening the helper keeps the complete exact request');
    assert.ok(expandedRequest.height <= 340 && expandedRequest.scroll > expandedRequest.client,'an expanded long request remains bounded and readable by scrolling');
    console.log('Helper delegation native two-line clamp and expandable exact request checks passed.');
    await js(`window.fixture.showUserText()`);
    await ready(`document.querySelector('.user-message-text') && document.querySelector('.bubble-assistant strong')`);
    const literal = await js(`(()=>{const node=document.querySelector('.user-message-text');return {expected:window.fixture.originalUserText,visible:node.innerText,text:node.textContent,whiteSpace:getComputedStyle(node).whiteSpace,scroll:node.scrollWidth,client:node.clientWidth,markup:node.querySelectorAll('code,strong,script').length,all:document.body.textContent}})()`);
    assert.equal(literal.visible,literal.expected,'native visible user text preserves Windows paths, backticks, blank lines and indentation');
    assert.equal(literal.text,literal.expected,'the original user characters remain unchanged');
    assert.equal(literal.whiteSpace,'pre-wrap');
    assert.ok(literal.scroll<=literal.client+1,'long Windows paths wrap within the user bubble');
    assert.equal(literal.markup,0,'user text stays escaped and unformatted');
    assert.doesNotMatch(literal.all,/INTERNAL MODEL NOTE/);
    assert.equal(await js(`document.querySelector('.bubble-assistant .message-body strong').textContent`),'bold','assistant Markdown remains formatted');
    assert.equal(await js(`document.querySelector('.bubble-assistant .message-body code').textContent`),'code');
    console.log('Native literal user paths, backticks, whitespace and model-only context checks passed.');
    console.log('Source reference native geometry, exact range, failure and keyboard checks passed.');
  } finally { win.webContents.setZoomFactor(1); win.destroy(); app.quit(); }
}).catch(error => { console.error(error); app.exit(1); });
