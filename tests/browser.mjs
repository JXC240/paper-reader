// Real mouse selection, downloads, persistence, failed saves, and real-paper smoke test.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn, execFileSync } from 'node:child_process';
import { createRequire } from 'node:module';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(process.env.PAPER_READER_NODE_MODULES ? path.join(process.env.PAPER_READER_NODE_MODULES, '_resolver.cjs') : import.meta.url);
const { chromium } = require('playwright');
const dataDir = await fs.mkdtemp(path.join(os.tmpdir(), 'paper-reader-e2e-'));
const output = path.join(root, 'test-results');
await fs.mkdir(output, {recursive:true});
const python = process.env.PAPER_READER_PYTHON || path.join(root,'.venv/bin/python');
const results = [], consoleErrors = [];
let service, browser, base, browserContext, page;

async function startServer(port = 0) {
  service = spawn(python, ['server.py', '--port',String(port),'--data-dir',dataDir], {cwd:root, stdio:['ignore','pipe','pipe']});
  base = await new Promise((resolve,reject)=>{let stdout='';const timeout=setTimeout(()=>reject(new Error('Server startup timeout')),15000);service.once('exit',code=>reject(new Error(`Server exited ${code}`)));service.stdout.on('data',chunk=>{stdout+=chunk;const match=stdout.match(/http:\/\/127\.0\.0\.1:\d+/);if(match){clearTimeout(timeout);resolve(match[0]);}});service.stderr.on('data',chunk=>process.stderr.write(chunk));});
}
async function stopServer() { const child=service;if(!child||child.exitCode!==null)return;await new Promise(resolve=>{child.once('exit',resolve);child.kill('SIGTERM');}); }
async function record(name, operation) { await operation(); results.push({name,passed:true});console.log('PASS',name); }
async function saved() { await page.waitForFunction(()=>document.querySelector('#save-status').textContent==='已保存到本机'); }
async function zoomRendered(value) {
  await page.waitForFunction(expected=>document.querySelector('#pdf-page').dataset.zoom===String(expected)&&document.querySelector('#page-loading').hidden,value);
  await saved();
  assert.equal((await activeRecord()).position.zoom,value);
}
async function setZoom(label, value) { await page.fill('#zoom',label);await page.press('#zoom','Enter');await zoomRendered(value); }
async function searchFor(query) {
  await page.click('#search-toggle'); await page.fill('#search-input',query); await page.click('#search-submit');
  await page.waitForFunction(()=>document.querySelector('#search-status').dataset.state==='ready');
}
async function chooseSearchResult(index) {
  await page.locator(`.search-result[data-index="${index}"]`).click();
  await page.waitForFunction(index=>Boolean(document.querySelector(`.search-rect.current[data-index="${index}"]`))&&document.querySelector('#page-loading').hidden,index);
  await saved();
}
async function paneAnchor() { return page.evaluate(()=>{const reader=document.querySelector('#reader-scroll'),r=reader.getBoundingClientRect(),p=document.querySelector('#pdf-page').getBoundingClientRect();return {x:(r.left+reader.clientWidth/2-p.left)/p.width,y:(r.top+reader.clientHeight/2-p.top)/p.height};}); }
async function count() { const session=await(await fetch(base+'/api/session')).json();return (await(await fetch(base+`/api/documents/${session.activeId}/record`)).json()).highlights.length; }
async function activeRecord() { const session=await(await fetch(base+'/api/session')).json();return (await(await fetch(base+`/api/documents/${session.activeId}/record`)).json()); }
async function dragSpan(fragment) {
  const span=page.locator('#text-layer span').filter({hasText:fragment}).first();await span.waitFor();await span.scrollIntoViewIfNeeded();
  const box=await span.boundingBox();assert(box&&box.width>10,'Text layer must be selectable');
  await page.mouse.move(box.x+1,box.y+box.height/2);await page.mouse.down();await page.mouse.move(box.x+box.width-1,box.y+box.height/2,{steps:12});await page.mouse.up();
}
async function dragAcross(firstText,lastText) {
  const first=page.locator('#text-layer span').filter({hasText:firstText}).first();const last=page.locator('#text-layer span').filter({hasText:lastText}).first();
  await first.scrollIntoViewIfNeeded();const a=await first.boundingBox(),b=await last.boundingBox();
  await page.mouse.move(a.x+1,a.y+a.height/2);await page.mouse.down();await page.mouse.move(b.x+b.width-1,b.y+b.height/2,{steps:18});await page.mouse.up();
}
async function dragWord(fragment) {
  const span=page.locator('#text-layer span').filter({hasText:fragment}).first();await span.scrollIntoViewIfNeeded();
  const box=await span.evaluate((element,word)=>{const node=element.firstChild;const offset=node.textContent.indexOf(word);const range=document.createRange();range.setStart(node,offset);range.setEnd(node,offset+word.length);const r=range.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height};},fragment);
  await page.mouse.move(box.x+.2,box.y+box.height/2);await page.mouse.down();await page.mouse.move(box.x+box.width-.2,box.y+box.height/2,{steps:12});await page.mouse.up();
}

try {
  await startServer();
  browser=await chromium.launch({headless:true,...(process.env.PAPER_READER_BROWSER_CHANNEL&&process.env.PAPER_READER_BROWSER_CHANNEL!=='bundled'?{channel:process.env.PAPER_READER_BROWSER_CHANNEL}:{})});
  browserContext=await browser.newContext({viewport:{width:1280,height:900},acceptDownloads:true});
  page=await browserContext.newPage();page.on('pageerror',err=>consoleErrors.push(err.message));
  await record('empty library and original demo import',async()=>{
    await page.goto(base);await page.locator('#empty-state').waitFor({state:'visible'});await page.click('#open-demo');await page.locator('#text-layer span').first().waitFor();await saved();
    assert.equal((await activeRecord()).pageCount,2);await page.screenshot({path:path.join(output,'reader-demo.png')});
  });
  await record('actual mouse selection creates a persistent highlight',async()=>{
    await dragSpan('A highlight');await page.waitForFunction(()=>document.querySelector('#highlight-count').textContent==='1');await saved();const item=(await activeRecord()).highlights[0];assert.match(item.rawText,/highlight/);assert(item.quads.length>0);assert.match(item.rawText+item.contextAfter,/A highlight is a question waiting to be understood/);assert.match(item.contextAfter,/does not mean/);
    await page.screenshot({path:path.join(output,'reader-highlight.png')});
  });
  await record('multiline and both columns retain reading order',async()=>{
    await dragAcross('Reading slowly','familiar.');await page.waitForFunction(()=>document.querySelector('#highlight-count').textContent==='2');await saved();const multiline=(await activeRecord()).highlights.at(-1);assert(multiline.quads.length>=2);assert.match(multiline.rawText,/familiar/);
    await dragSpan('A saved annotation');await page.waitForFunction(()=>document.querySelector('#highlight-count').textContent==='3');await saved();const r=await activeRecord();const markdown=await(await fetch(base+`/api/documents/${r.id}/markdown`)).text();assert(markdown.indexOf('> Reading slowly')<markdown.indexOf('> A saved annotation'));
    await page.locator('.highlight-card').last().getByRole('button',{name:'删除',exact:true}).click();await saved();await page.locator('.highlight-card').last().getByRole('button',{name:'删除',exact:true}).click();await saved();assert.equal(await count(),1);
  });
  await record('zoom preserves PDF coordinates and visible alignment',async()=>{
    const before=(await activeRecord()).highlights[0].quads;const oldBounds=await page.locator('.highlight-rect').first().boundingBox();const oldPage=await page.locator('#pdf-page').boundingBox();await setZoom('137.5%',1.375);const after=(await activeRecord()).highlights[0].quads;assert.deepEqual(after,before);
    const highlight=await page.locator('.highlight-rect').first().boundingBox();const newPage=await page.locator('#pdf-page').boundingBox();const ratio=newPage.width/oldPage.width;
    assert(Math.abs(highlight.x-newPage.x-(oldBounds.x-oldPage.x)*ratio)<1);
    assert(Math.abs(highlight.y-newPage.y-(oldBounds.y-oldPage.y)*ratio)<1);
    assert(Math.abs(highlight.width-oldBounds.width*ratio)<1);
    assert(Math.abs(highlight.height-oldBounds.height*ratio)<1);
    const text=await page.locator('#text-layer span').filter({hasText:'A highlight'}).first().boundingBox();assert(text.y+text.height/2>highlight.y&&text.y+text.height/2<highlight.y+highlight.height);
  });
  await record('refresh and new browser page restore highlighter and reading position',async()=>{
    await page.click('#next-page');await page.locator('#text-layer span').filter({hasText:'Keep the context'}).first().waitFor();await saved();await page.reload();await saved();assert.equal(await page.inputValue('#page-number'),'2');assert.equal(await page.inputValue('#zoom'),'137.5%');assert.equal(await count(),1);
    await page.close();page=await browserContext.newPage();page.on('pageerror',err=>consoleErrors.push(err.message));await page.goto(base);await saved();assert.equal(await page.inputValue('#page-number'),'2');assert.equal(await count(),1);
  });
  await record('custom zoom, rapid buttons, shortcuts, limits, and reading anchor',async()=>{
    await setZoom('150',1.5);await page.locator('#reader-scroll').hover();await page.mouse.wheel(0,420);await page.waitForTimeout(150);
    const anchor=await page.evaluate(()=>{const reader=document.querySelector('#reader-scroll'),r=reader.getBoundingClientRect(),p=document.querySelector('#pdf-page').getBoundingClientRect();return (r.top+reader.clientHeight/2-p.top)/p.height;});
    await setZoom('170%',1.7);
    const moved=await page.evaluate(()=>{const reader=document.querySelector('#reader-scroll'),r=reader.getBoundingClientRect(),p=document.querySelector('#pdf-page').getBoundingClientRect();return (r.top+reader.clientHeight/2-p.top)/p.height;});
    assert(Math.abs(anchor-moved)<.002,'Zoom keeps the same PDF point at the reading pane center');
    await setZoom('100%',1);for(let i=0;i<3;i++)await page.click('#zoom-in');await zoomRendered(1.3);
    await page.click('#zoom-out');await zoomRendered(1.2);
    await page.locator('#reader-scroll').focus();await page.keyboard.press('Meta+=');await zoomRendered(1.3);await page.keyboard.press('Meta+-');await zoomRendered(1.2);await page.keyboard.press('Control+=');await zoomRendered(1.3);await page.keyboard.press('Control+-');await zoomRendered(1.2);await page.keyboard.press('Meta+0');await zoomRendered('fit');
    await setZoom('25%',.25);assert(await page.locator('#zoom-out').isDisabled());await setZoom('400%',4);assert(await page.locator('#zoom-in').isDisabled());
    await page.fill('#zoom','500%');await page.press('#zoom','Enter');assert.equal(await page.inputValue('#zoom'),'400%');assert.equal((await activeRecord()).position.zoom,4);
    await page.fill('#zoom','abc');await page.press('#zoom','Enter');assert.equal(await page.inputValue('#zoom'),'400%');
    await page.click('#zoom-fit');await zoomRendered('fit');assert.match(await page.inputValue('#zoom'),/^\d+(\.\d+)?%$/);assert.equal(await page.getAttribute('#zoom-fit','aria-pressed'),'true');
  });
  await record('failed save remains visible and retries without duplicates',async()=>{
    await page.click('#zoom-fit');await saved();await page.route('**/highlights',route=>route.abort());await dragSpan('A single word');await page.locator('#retry-save').waitFor({state:'visible'});assert.equal(await count(),1);assert.equal(await page.locator('.highlight-card').count(),2);
    await page.unroute('**/highlights');await page.click('#retry-save');await saved();assert.equal(await count(),2);
  });
  await record('single-word highlight preserves the surrounding full sentence',async()=>{
    await dragWord('surrounding');await page.waitForFunction(()=>document.querySelector('#highlight-count').textContent==='3');await saved();const h=(await activeRecord()).highlights.at(-1);assert.equal(h.rawText,'surrounding');assert.match(h.contextBefore,/selected word and the/);assert.match(h.contextAfter,/original text/);
    await page.locator('.highlight-card').last().getByRole('button',{name:'删除',exact:true}).click();await saved();assert.equal(await count(),2);
  });
  await record('selection mode requires explicit highlight and honors color',async()=>{
    await page.click('#highlight-toggle');await dragWord('nearby');await page.locator('#selection-menu').waitFor({state:'visible'});assert.equal(await count(),2);await page.selectOption('#highlight-color','green');await page.click('#highlight-selection');await page.waitForFunction(()=>document.querySelector('#highlight-count').textContent==='3');await saved();assert.equal((await activeRecord()).highlights.at(-1).color,'green');
    await page.locator('.highlight-card').last().getByRole('button',{name:'删除',exact:true}).click();await saved();await page.click('#highlight-toggle');await page.selectOption('#highlight-color','yellow');
  });
  await record('canceled selection never leaves an obstructing menu or adds a highlight',async()=>{
    await page.click('#highlight-toggle');
    const popup=page.locator('#selection-menu');
    await dragWord('nearby');await popup.waitFor({state:'visible'});await page.locator('#pdf-page').click({position:{x:8,y:8}});await popup.waitFor({state:'hidden'});
    await dragWord('nearby');await popup.waitFor({state:'visible'});await page.keyboard.press('Escape');await popup.waitFor({state:'hidden'});assert.equal(await page.evaluate(()=>window.getSelection().isCollapsed),true);
    // Chromium does not consistently collapse non-editable PDF selections with ArrowLeft.
    // Use the browser selection API to exercise a range canceled outside our menu handlers.
    await dragWord('nearby');await popup.waitFor({state:'visible'});await page.evaluate(()=>window.getSelection().removeAllRanges());await popup.waitFor({state:'hidden'});
    await dragWord('nearby');await popup.waitFor({state:'visible'});await page.locator('#reader-scroll').hover();await page.mouse.wheel(0,170);await popup.waitFor({state:'hidden'});
    await dragWord('nearby');await popup.waitFor({state:'visible'});await page.click('#cancel-selection');await popup.waitFor({state:'hidden'});
    await browserContext.grantPermissions(['clipboard-read','clipboard-write'],{origin:base});await dragWord('nearby');await popup.waitFor({state:'visible'});await page.click('#copy-selection');await popup.waitFor({state:'hidden'});assert.equal(await page.evaluate(()=>navigator.clipboard.readText()),'nearby');
    assert.equal(await count(),2);await page.click('#highlight-toggle');
  });
  await record('seven colors, underline, strikeout, restyling, zoom, and portable export',async()=>{
    assert.deepEqual(await page.locator('#highlight-color option').evaluateAll(options=>options.map(o=>o.value)),['yellow','green','pink','blue','purple','orange','red']);
    await page.selectOption('#highlight-style','underline');await page.selectOption('#highlight-color','blue');await dragWord('nearby');await page.waitForFunction(()=>document.querySelector('#highlight-count').textContent==='3');await saved();
    const underline=(await activeRecord()).highlights.at(-1);assert.equal(underline.style,'underline');assert.equal(underline.color,'blue');
    let mark=page.locator(`[data-highlight-id="${underline.id}"]`).first();assert.equal(await mark.getAttribute('data-style'),'underline');assert.equal(await mark.evaluate(e=>getComputedStyle(e).borderBottomColor),'rgb(39, 109, 182)');
    const oldBox=await mark.boundingBox();await setZoom('175%',1.75);assert.deepEqual((await activeRecord()).highlights.at(-1).quads,underline.quads);mark=page.locator(`[data-highlight-id="${underline.id}"]`).first();assert((await mark.boundingBox()).width>oldBox.width);
    await page.click('#zoom-fit');await zoomRendered('fit');await page.selectOption('#highlight-style','strikeout');await page.selectOption('#highlight-color','red');await dragWord('surrounding');await page.waitForFunction(()=>document.querySelector('#highlight-count').textContent==='4');await saved();
    const strike=(await activeRecord()).highlights.at(-1);assert.equal(strike.style,'strikeout');assert.equal(strike.color,'red');assert.equal(strike.rawText,'surrounding');
    const line=page.locator(`[data-highlight-id="${strike.id}"]`).first();assert.equal(await line.evaluate(e=>getComputedStyle(e,'::after').backgroundColor),'rgb(195, 63, 69)');
    await page.screenshot({path:path.join(output,'annotation-styles.png')});await page.reload();await saved();assert.equal(await count(),4);assert(await page.locator('.annotation-underline').count()>0);assert(await page.locator('.annotation-strikeout').count()>0);
    const markdown=await(await fetch(base+`/api/documents/${(await activeRecord()).id}/markdown`)).text();assert.match(markdown,/标注：下划线 · 蓝色/);assert.match(markdown,/标注：删除线 · 红色/);
    const promise=page.waitForEvent('download');await page.click('#export-pdf');await (await promise).saveAs(path.join(output,'styled-annotated.pdf'));
    const strikeCard=page.locator(`.highlight-card[data-id="${strike.id}"]`);
    await strikeCard.getByLabel('此标注方式').selectOption('underline');await saved();await strikeCard.getByLabel('此标注颜色').selectOption('purple');await saved();
    const changed=(await activeRecord()).highlights.at(-1);assert.equal(changed.style,'underline');assert.equal(changed.color,'purple');assert.deepEqual(changed.quads,strike.quads);
    await strikeCard.getByRole('button',{name:'删除',exact:true}).click();await saved();await page.click('#undo');await saved();const restored=(await activeRecord()).highlights.at(-1);assert.equal(restored.style,'underline');assert.equal(restored.color,'purple');
    for(const id of [restored.id,underline.id]){await page.locator(`.highlight-card[data-id="${id}"]`).getByRole('button',{name:'删除',exact:true}).click();await saved();}assert.equal(await count(),2);
    await page.selectOption('#highlight-style','highlight');await page.selectOption('#highlight-color','yellow');await page.click('#zoom-fit');await zoomRendered('fit');
  });
  await record('vocabulary classification and optional note persist',async()=>{
    const card=page.locator('.highlight-card').last();await card.getByRole('button',{name:'收为生词'}).click();await saved();
    const updated=page.locator('.highlight-card').last();await updated.locator('summary').click();await updated.locator('textarea').fill('读者确认的测试笔记。');await updated.getByRole('button',{name:'保存笔记'}).click();await saved();const last=(await activeRecord()).highlights.at(-1);assert.equal(last.kind,'vocabulary');assert.equal(last.note,'读者确认的测试笔记。');
  });
  await record('unsaved typed notes survive zoom, filtering, paging, reload, and document-scoped draft recovery',async()=>{
    const original=(await activeRecord()).highlights.at(-1),card=page.locator(`.highlight-card[data-id="${original.id}"]`),draft='先自己理解：这是一条尚未保存的阅读草稿。';
    await card.locator('summary').click();await card.locator('textarea').fill(draft);
    await page.locator('#draft-status').waitFor({state:'visible'});assert.match(await card.locator('summary').textContent(),/尚未保存/);
    await setZoom('125%',1.25);assert.equal(await card.locator('textarea').inputValue(),draft);
    await page.selectOption('#highlight-filter','page');await page.click('#previous-page');await page.waitForFunction(()=>document.querySelector('#page-number').value==='1'&&document.querySelector('#page-loading').hidden);await saved();assert.equal(await card.count(),0);
    await page.selectOption('#highlight-filter','all');assert.equal(await card.locator('textarea').inputValue(),draft);
    assert.equal((await activeRecord()).highlights.find(h=>h.id===original.id).note,original.note,'A draft must not silently save an unconfirmed explanation');
    assert(await page.evaluate(()=>{const event=new Event('beforeunload',{cancelable:true});window.dispatchEvent(event);return event.defaultPrevented;}),'Unsaved drafts warn before leaving');
    const accept=dialog=>dialog.accept();page.on('dialog',accept);
    try { await page.reload();await saved(); } finally {page.off('dialog',accept);}
    if(await page.locator('#sidebar').isHidden())await page.click('#sidebar-toggle');await page.locator('#notes-panel').waitFor({state:'visible'});
    assert.equal(await card.locator('textarea').inputValue(),draft);assert(await card.locator('details').evaluate(e=>e.open));
    await card.getByRole('button',{name:'保存笔记'}).click();await saved();assert.equal((await activeRecord()).highlights.find(h=>h.id===original.id).note,draft);assert(await page.locator('#draft-status').isHidden());
    await card.locator('summary').click();await card.locator('textarea').fill(original.note);await card.getByRole('button',{name:'保存笔记'}).click();await saved();
    await page.click('#next-page');await page.waitForFunction(()=>document.querySelector('#page-number').value==='2'&&document.querySelector('#page-loading').hidden);await saved();await page.click('#zoom-fit');await zoomRendered('fit');
  });
  await record('finishing an older note save preserves text typed while that save is in flight',async()=>{
    const original=(await activeRecord()).highlights.at(-1),card=page.locator(`.highlight-card[data-id="${original.id}"]`),url=base+`/api/documents/${(await activeRecord()).id}/highlights/${original.id}`;
    let release,entered;const wait=new Promise(resolve=>{release=resolve;}),started=new Promise(resolve=>{entered=resolve;});
    await page.route(url,async route=>{if(route.request().method()==='PATCH'){entered();await wait;}await route.continue();});
    try {
      await card.locator('summary').click();await card.locator('textarea').fill('第一版：点击保存时的内容。');await card.getByRole('button',{name:'保存笔记'}).click();await started;
      await card.locator('textarea').fill('第二版：保存过程中继续输入的内容。');release();await saved();
      assert.equal((await activeRecord()).highlights.find(h=>h.id===original.id).note,'第一版：点击保存时的内容。');
      assert.equal(await card.locator('textarea').inputValue(),'第二版：保存过程中继续输入的内容。');assert(await page.locator('#draft-status').isVisible());
    } finally {release();await page.unroute(url);}
    await card.locator('textarea').fill(original.note);await card.getByRole('button',{name:'保存笔记'}).click();await saved();assert(await page.locator('#draft-status').isHidden());
  });
  await record('failed note saves retain drafts and retry the explicit saved text',async()=>{
    const original=(await activeRecord()).highlights.at(-1),card=page.locator(`.highlight-card[data-id="${original.id}"]`),url=base+`/api/documents/${(await activeRecord()).id}/highlights/${original.id}`,draft='网络失败时也必须保留的阅读草稿。';
    await page.route(url,route=>route.abort());
    try {
      await card.locator('summary').click();await card.locator('textarea').fill(draft);await card.getByRole('button',{name:'保存笔记'}).click();await page.locator('#retry-save').waitFor({state:'visible'});
      assert.equal(await card.locator('textarea').inputValue(),draft);assert.equal((await activeRecord()).highlights.find(h=>h.id===original.id).note,original.note);assert(await page.locator('#draft-status').isVisible());
    } finally {await page.unroute(url);}
    await page.click('#retry-save');await saved();assert.equal((await activeRecord()).highlights.find(h=>h.id===original.id).note,draft);assert(await page.locator('#draft-status').isHidden());
    await card.locator('summary').click();await card.locator('textarea').fill(original.note);await card.getByRole('button',{name:'保存笔记'}).click();await saved();
  });
  await record('blocked browser draft storage warns clearly and still protects text through rerenders',async()=>{
    const original=(await activeRecord()).highlights.at(-1),card=page.locator(`.highlight-card[data-id="${original.id}"]`),draft='浏览器暂存被禁用时，当前页面内仍要保留。';
    await page.evaluate(()=>{window.readerTestStorageSetItem=Storage.prototype.setItem;Storage.prototype.setItem=function(){throw new DOMException('Test quota failure','QuotaExceededError');};});
    try {
      await card.locator('summary').click();await card.locator('textarea').fill(draft);await page.locator('#error-banner').waitFor({state:'visible'});assert.match(await page.locator('#error-text').textContent(),/浏览器无法保存笔记草稿/);
      await setZoom('125%',1.25);assert.equal(await card.locator('textarea').inputValue(),draft);assert.match(await page.locator('#draft-status').textContent(),/仅在当前页面/);
    } finally {await page.evaluate(()=>{Storage.prototype.setItem=window.readerTestStorageSetItem;delete window.readerTestStorageSetItem;});}
    await card.locator('textarea').fill(original.note);await card.getByRole('button',{name:'保存笔记'}).click();await saved();await page.click('#dismiss-error');await page.click('#zoom-fit');await zoomRendered('fit');
  });
  await record('Markdown and standard annotated PDF downloads',async()=>{
    let promise=page.waitForEvent('download');await page.click('#export-markdown');let download=await promise;await download.saveAs(path.join(output,'demo-notes.md'));const markdown=await fs.readFile(path.join(output,'demo-notes.md'),'utf8');assert.match(markdown,/读者确认的生词/);assert.match(markdown,/读者确认的测试笔记/);
    promise=page.waitForEvent('download');await page.click('#export-pdf');download=await promise;await download.saveAs(path.join(output,'demo-annotated.pdf'));const bytes=await fs.readFile(path.join(output,'demo-annotated.pdf'));assert.equal(bytes.subarray(0,5).toString(),'%PDF-');
  });
  await record('copying reading notes produces full source context',async()=>{
    await browserContext.grantPermissions(['clipboard-read','clipboard-write'],{origin:base});await page.click('#copy-all');await page.waitForFunction(()=>!document.querySelector('#toast').hidden&&document.querySelector('#toast').textContent.includes('已复制'));
    const text=await page.evaluate(()=>navigator.clipboard.readText());assert.match(text,/PDF 第 2 页/);assert.match(text,/附近原文/);assert.match(text,/读者确认的测试笔记/);assert.match(text,/论文编号：[0-9a-f]{64}/);assert.match(text,/固定阅读链接：http:\/\/127\.0\.0\.1:\d+\/\?doc=[0-9a-f]{64}/);assert.match(text,/documents\/[0-9a-f]{64}\/record\.json/);
  });
  await record('library backup button downloads a portable archive',async()=>{
    const promise=page.waitForEvent('download');await page.click('#backup-library');const backup=await promise;await backup.saveAs(path.join(output,'library-backup.zip'));
    assert.match(backup.suggestedFilename(),/^paper-reader-backup-\d{4}-\d{2}-\d{2}\.zip$/);assert.equal((await fs.readFile(path.join(output,'library-backup.zip'))).subarray(0,2).toString(),'PK');
  });
  await record('delete and undo restore selected text',async()=>{
    const original=(await activeRecord()).highlights.at(-1).rawText;await page.locator('.highlight-card').last().getByRole('button',{name:'删除',exact:true}).click();await saved();assert.equal(await count(),1);await page.click('#undo');await saved();assert.equal(await count(),2);assert.equal((await activeRecord()).highlights.at(-1).rawText,original);
  });
  await record('literal full-document search locates both pages without creating annotations',async()=>{
    const original=(await activeRecord()).highlights;
    await searchFor('word'); const hits=await page.locator('.search-result').count(); assert(hits>=3);
    assert(await page.locator('.search-result small').filter({hasText:'第 1 页'}).count()>0);
    assert(await page.locator('.search-result small').filter({hasText:'第 2 页'}).count()>0);
    await chooseSearchResult(0); assert.equal(await page.inputValue('#page-number'),'1');
    const rect=page.locator('.search-rect.current').first(),box=await rect.boundingBox();assert(box&&box.width>10&&box.height>5);
    assert(await page.evaluate(()=>{const r=document.querySelector('.search-rect.current').getBoundingClientRect();return [...document.querySelectorAll('#text-layer span')].some(e=>{const t=e.getBoundingClientRect(),middle=r.y+r.height/2;return e.textContent.toLowerCase().includes('word')&&r.x>=t.x-1&&r.right<=t.right+1&&middle>=t.y-2&&middle<=t.bottom+2;});}),'Search box aligns with the original text run');
    await page.screenshot({path:path.join(output,'reader-search.png')});
    const quads=await rect.evaluate(e=>({left:parseFloat(e.style.left),width:parseFloat(e.style.width)}));
    const oldPageWidth=(await page.locator('#pdf-page').boundingBox()).width;await setZoom('175%',1.75);
    const resized=await page.locator('.search-rect.current').first().evaluate(e=>({left:parseFloat(e.style.left),width:parseFloat(e.style.width)}));
    const ratio=(await page.locator('#pdf-page').boundingBox()).width/oldPageWidth;
    assert(Math.abs(resized.width-quads.width*ratio)<1);assert(Math.abs(resized.left-quads.left*ratio)<1);
    await page.locator('#search-input').focus();await page.keyboard.press('Enter');await page.waitForFunction(()=>document.querySelector('.search-result[aria-current="true"]').dataset.index==='1');
    await page.keyboard.press('Shift+Enter');await page.waitForFunction(()=>document.querySelector('.search-result[aria-current="true"]').dataset.index==='0');
    assert.deepEqual((await activeRecord()).highlights,original);
    await page.click('#search-clear');assert.equal(await page.locator('.search-rect').count(),0);assert.equal(await page.locator('.search-result').count(),0);
  });
  await record('search case folding, cross-line phrase, no result, shortcuts, and cancellation',async()=>{
    await searchFor('A HIGHLIGHT IS A QUESTION WAITING TO BE UNDERSTOOD. IT DOES NOT MEAN THAT THE READER HAS ALREADY LEARNED THE SENTENCE.');assert.equal(await page.locator('.search-result').count(),1);await chooseSearchResult(0);assert(await page.locator('.search-rect.current').count()>=2);
    await searchFor('not-in-this-document[.*]');assert.equal(await page.locator('.search-result').count(),0);assert(await page.locator('#search-next').isDisabled());assert.match(await page.locator('#search-status').textContent(),/没有找到/);
    await page.locator('#reader-scroll').focus();await page.keyboard.press('Meta+f');assert(await page.locator('#search-input').evaluate(e=>document.activeElement===e));
    await page.keyboard.press('Escape');await page.locator('#sidebar').waitFor({state:'hidden'});
    await page.click('#zoom-fit');await zoomRendered('fit');await page.click('#sidebar-toggle');await page.locator('#notes-panel').waitFor({state:'visible'});
  });
  await record('page bookmarks persist, rename, navigate, and delete independently of annotations',async()=>{
    const original=(await activeRecord()).highlights;
    await page.fill('#page-number','1');await page.press('#page-number','Tab');await page.waitForFunction(()=>document.querySelector('#page-number').value==='1'&&document.querySelector('#page-loading').hidden);await saved();
    await page.click('#bookmark-toggle');await saved();assert.equal((await activeRecord()).bookmarks.length,1);assert.equal(await page.getAttribute('#bookmark-toggle','aria-pressed'),'true');
    await page.click('#navigation-toggle');await page.locator('#navigation-panel').waitFor({state:'visible'});assert.match(await page.locator('#outline-status').textContent(),/没有内置目录/);
    const bookmark=page.locator('.bookmark-card[data-page="1"]');await bookmark.locator('input').fill('Methods worth revisiting');await bookmark.getByRole('button',{name:'保存名称'}).click();await saved();
    await page.click('#next-page');await page.waitForFunction(()=>document.querySelector('#page-number').value==='2'&&document.querySelector('#page-loading').hidden);await saved();assert.equal(await page.getAttribute('#bookmark-toggle','aria-pressed'),'false');
    await page.reload();await saved();await page.click('#navigation-toggle');assert.equal(await bookmark.locator('input').inputValue(),'Methods worth revisiting');
    await bookmark.getByRole('button',{name:'第 1 页',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#page-number').value==='1'&&document.querySelector('#page-loading').hidden);await saved();assert.equal(await page.getAttribute('#bookmark-toggle','aria-pressed'),'true');
    await bookmark.getByRole('button',{name:'删除',exact:true}).click();await saved();assert.equal((await activeRecord()).bookmarks.length,0);assert.deepEqual((await activeRecord()).highlights,original);
  });
  await record('page-inner reading anchor survives refresh, pane changes, and a new browser tab',async()=>{
    await setZoom('170%',1.7);await page.locator('#reader-scroll').evaluate(e=>{e.scrollTop=420;e.scrollLeft=120;});
    await page.waitForTimeout(550);await saved();const original=await paneAnchor(),stored=(await activeRecord()).position.anchor;
    assert(Math.abs(stored.y-original.y)<.003);assert(Math.abs(stored.x-original.x)<.003);
    await page.reload();await saved();const restored=await paneAnchor();assert(Math.abs(restored.y-original.y)<.003);assert(Math.abs(restored.x-original.x)<.003);
    await page.click('#sidebar-toggle');await page.click('#sidebar-toggle');const changed=await paneAnchor();assert(Math.abs(changed.y-original.y)<.003);
    await page.close();page=await browserContext.newPage();page.on('pageerror',err=>consoleErrors.push(err.message));await page.goto(base);await saved();assert(Math.abs((await paneAnchor()).y-original.y)<.003);
    await page.fill('#page-number','2');await page.press('#page-number','Tab');await page.waitForFunction(()=>document.querySelector('#page-number').value==='2'&&document.querySelector('#page-loading').hidden);await saved();
  });
  await record('built-in nested PDF outline navigates and document switching clears search and bookmarks',async()=>{
    const oldId=(await activeRecord()).id,fixture=path.join(output,'demo-with-outline.pdf');
    execFileSync(python,['-c','import sys; from pypdf import PdfWriter; w=PdfWriter(clone_from=sys.argv[1]); root=w.add_outline_item("Demo reading",0); w.add_outline_item("Context section",1,parent=root); w.write(sys.argv[2])',path.join(root,'examples/reader-demo.pdf'),fixture]);
    await searchFor('reader');await page.setInputFiles('#file-input',fixture);await saved();await page.waitForFunction(()=>document.querySelector('#outline-list button')?.textContent==='Demo reading');
    assert.equal(await page.locator('.search-result').count(),0);assert.equal(await page.locator('#search-input').inputValue(),'');assert.equal((await activeRecord()).bookmarks.length,0);
    await page.click('#navigation-toggle');await page.locator('#outline-list button').filter({hasText:'Context section'}).click();await page.waitForFunction(()=>document.querySelector('#page-number').value==='2'&&document.querySelector('#page-loading').hidden);await saved();
    await page.locator('#outline-list button').filter({hasText:'Demo reading'}).click();await page.waitForFunction(()=>document.querySelector('#page-number').value==='1'&&document.querySelector('#page-loading').hidden);await saved();
    await page.selectOption('#document-picker',oldId);await page.waitForFunction(id=>document.querySelector('#document-picker').value===id&&!document.querySelector('#document-picker').disabled&&document.querySelector('#page-loading').hidden,oldId);await saved();assert.equal(await page.inputValue('#page-number'),'2');assert.equal(await count(),2);
    await page.click('#sidebar-toggle');await page.click('#zoom-fit');await zoomRendered('fit');
  });
  await record('fixed document links stay bound across chats and reject missing documents without fallback',async()=>{
    const original=await activeRecord(),session=await(await fetch(base+'/api/session')).json(),other=session.documents.find(doc=>doc.id!==original.id);
    assert(other,'The test library must contain a second PDF');assert.equal(new URL(page.url()).searchParams.get('doc'),original.id);
    const card=page.locator(`.highlight-card[data-id="${original.highlights.at(-1).id}"]`),draft='只属于第一篇论文的未保存草稿。';
    await card.locator('summary').click();await card.locator('textarea').fill(draft);
    await page.selectOption('#document-picker',other.id);await saved();assert.equal(await page.locator('.highlight-card textarea').count(),0,'A draft must not leak into another PDF');
    await page.selectOption('#document-picker',original.id);await saved();assert.equal(await card.locator('textarea').inputValue(),draft);
    await card.locator('textarea').fill(original.highlights.at(-1).note||'');await card.getByRole('button',{name:'保存笔记'}).click();await saved();
    await browserContext.grantPermissions(['clipboard-read','clipboard-write'],{origin:base});await page.click('#copy-document-link');assert.equal(new URL(await page.evaluate(()=>navigator.clipboard.readText())).searchParams.get('doc'),original.id);
    const second=await browserContext.newPage();second.on('pageerror',err=>consoleErrors.push(err.message));
    try {
      await second.goto(base+'/?doc='+other.id);await second.waitForFunction(()=>document.querySelector('#save-status').textContent==='已保存到本机');assert.equal((await activeRecord()).id,other.id);
      await page.reload();await saved();assert.equal(await page.inputValue('#document-picker'),original.id,'Reload honors its explicit document rather than the global active document');
      assert.equal(await second.inputValue('#document-picker'),other.id);
      const activeBefore=(await activeRecord()).id;
      await second.goto(base+'/?doc='+'f'.repeat(64));await second.locator('#error-banner').waitFor({state:'visible'});assert(await second.locator('#workspace').isHidden());assert.match(await second.locator('#error-text').textContent(),/没有切换到其他论文/);assert.equal((await activeRecord()).id,activeBefore);
    } finally {await second.close();}
  });
  await record('reading page shortcuts and keyboard help do not interrupt note editing',async()=>{
    await page.locator('#reader-scroll').focus();await page.keyboard.press('Home');await page.waitForFunction(()=>document.querySelector('#page-number').value==='1'&&document.querySelector('#page-loading').hidden);await saved();
    await page.keyboard.press('ArrowRight');await page.waitForFunction(()=>document.querySelector('#page-number').value==='2'&&document.querySelector('#page-loading').hidden);await saved();
    await page.keyboard.press('PageUp');await page.waitForFunction(()=>document.querySelector('#page-number').value==='1'&&document.querySelector('#page-loading').hidden);await saved();
    await page.keyboard.press('End');await page.waitForFunction(()=>document.querySelector('#page-number').value==='2'&&document.querySelector('#page-loading').hidden);await saved();
    await page.keyboard.press('?');assert(await page.locator('#help').isVisible());assert.equal(await page.getAttribute('#help-toggle','aria-expanded'),'true');await page.keyboard.press('Escape');assert(await page.locator('#help').isHidden());assert.equal(await page.getAttribute('#help-toggle','aria-expanded'),'false');
    const card=page.locator('.highlight-card').last();await card.locator('summary').click();await card.locator('textarea').focus();await page.keyboard.press('ArrowLeft');assert.equal(await page.inputValue('#page-number'),'2');await page.keyboard.press('PageUp');assert.equal(await page.inputValue('#page-number'),'2');
  });
  await record('empty text-layer notice and recovery after a failed PDF load',async()=>{
    const originalId=(await activeRecord()).id,fixture=path.join(output,'empty-text-layer.pdf');
    execFileSync(python,['-c','import sys; from pypdf import PdfWriter; w=PdfWriter(); w.add_blank_page(width=612,height=792); w.write(sys.argv[1])',fixture]);
    await page.route('**/api/documents/*/pdf',route=>route.abort());await page.setInputFiles('#file-input',fixture);await page.locator('#error-banner').waitFor({state:'visible'});
    assert(await page.locator('#document-picker').isEnabled(),'Failed loading must not lock the document picker');
    await page.unroute('**/api/documents/*/pdf');await page.setInputFiles('#file-input',fixture);await page.locator('#no-text').waitFor({state:'visible'});await saved();
    await searchFor('anything');assert.match(await page.locator('#search-status').textContent(),/没有可搜索的文本层/);assert.equal(await page.locator('.search-result').count(),0);
    await page.selectOption('#document-picker',originalId);await page.waitForFunction(id=>document.querySelector('#document-picker').value===id&&!document.querySelector('#document-picker').disabled&&document.querySelector('#page-loading').hidden,originalId);await saved();assert.equal(await count(),2);
    await page.click('#sidebar-toggle');
  });
  await record('rapid sidebar changes and paging share the rendering queue',async()=>{
    await page.click('#zoom-fit');await zoomRendered('fit');
    for(let i=0;i<3;i++){await page.click('#search-toggle');await page.click('#sidebar-close');}
    await page.click('#previous-page');await page.waitForFunction(()=>document.querySelector('#page-number').value==='1'&&document.querySelector('#page-loading').hidden);await saved();
    await page.click('#navigation-toggle');await page.click('#next-page');await page.waitForFunction(()=>document.querySelector('#page-number').value==='2'&&document.querySelector('#page-loading').hidden);await saved();
    assert(await page.locator('#error-banner').isHidden());
    await page.click('#sidebar-toggle');
  });
  await record('open page saves a mouse annotation after a real service restart without reloading',async()=>{
    await page.click('#zoom-fit');await zoomRendered('fit');
    await page.locator('#reader-scroll').evaluate(e=>e.scrollTop=0);await page.waitForTimeout(550);await saved();
    const original=await activeRecord(),originalBase=base,timeOrigin=await page.evaluate(()=>performance.timeOrigin);
    const oldSession=await(await fetch(base+'/api/session')).json();
    const highlightURL=base+`/api/documents/${original.id}/highlights`,posts=[];
    let sessionReads=0;
    const observe=request=>{if(request.url()===base+'/api/session')sessionReads++;if(request.url()===highlightURL&&request.method()==='POST')posts.push(request.postData());};
    page.on('request',observe);
    try {
      await stopServer();await startServer(Number(new URL(originalBase).port));
      assert.equal(base,originalBase);
      const newSession=await(await fetch(base+'/api/session')).json();
      assert(oldSession.token!==newSession.token,'Restart must rotate the session token');
      await dragWord('nearby');await page.waitForFunction(expected=>document.querySelector('#highlight-count').textContent===String(expected),original.highlights.length+1);await saved();
      const restored=await activeRecord();
      assert.equal(await page.evaluate(()=>performance.timeOrigin),timeOrigin,'The open page must not reload');
      assert.equal(restored.id,original.id);assert.equal(await page.inputValue('#document-picker'),original.id);
      assert.deepEqual(restored.highlights.slice(0,-1),original.highlights);
      assert.equal(restored.highlights.length,original.highlights.length+1);
      assert.equal(new Set(restored.highlights.map(item=>item.id)).size,restored.highlights.length);
      assert.equal(posts.length,2,'Only the rejected request and one replay are sent');assert.equal(posts[0],posts[1]);
      assert.equal(sessionReads,1,'The browser refreshes only the session token');
      assert(await page.locator('#error-banner').isHidden());
      await page.locator(`.highlight-card[data-id="${restored.highlights.at(-1).id}"]`).getByRole('button',{name:'删除',exact:true}).click();await saved();
      assert.deepEqual((await activeRecord()).highlights,original.highlights);
    } finally { page.off('request',observe); }
  });
  await record('non-token 403 does not refresh or replay and keeps the pending annotation',async()=>{
    const original=await activeRecord(),highlightURL=base+`/api/documents/${original.id}/highlights`;
    let attempts=0,sessionReads=0;
    const observe=request=>{if(request.url()===base+'/api/session')sessionReads++;};page.on('request',observe);
    await page.route(highlightURL,route=>{attempts++;return route.fulfill({status:403,contentType:'application/json',body:JSON.stringify({error:'不允许跨站访问'})});});
    try {
      await dragWord('nearby');await page.locator('#retry-save').waitFor({state:'visible'});await page.waitForTimeout(200);
      assert.equal(attempts,1);assert.equal(sessionReads,0);
      assert.match(await page.locator('#error-text').textContent(),/不允许跨站访问/);
      assert.equal((await activeRecord()).id,original.id);assert.equal(await count(),original.highlights.length);
      assert.equal(await page.locator('.highlight-card').count(),original.highlights.length+1);
      await page.unroute(highlightURL);await page.click('#retry-save');await saved();
      const restored=await activeRecord();assert.equal(restored.highlights.length,original.highlights.length+1);
      await page.locator(`.highlight-card[data-id="${restored.highlights.at(-1).id}"]`).getByRole('button',{name:'删除',exact:true}).click();await saved();
      assert.deepEqual((await activeRecord()).highlights,original.highlights);
    } finally { await page.unroute(highlightURL);page.off('request',observe); }
  });
  await record('concurrent expired requests share one session refresh and preserve download bodies',async()=>{
    const original=await activeRecord(),attempts=new Map(),exportRoute=/\/api\/documents\/[^/]+\/(markdown|annotated\.pdf)$/;
    let sessionReads=0,expiredResponses=0,release;
    const bothExpired=new Promise(resolve=>{release=resolve;});
    const sessionURL=base+'/api/session';
    await page.route(sessionURL,async route=>{sessionReads++;await bothExpired;await route.continue();});
    await page.route(exportRoute,route=>{
      const operation=new URL(route.request().url()).pathname.split('/').at(-1),attempt=(attempts.get(operation)||0)+1;attempts.set(operation,attempt);
      if(attempt!==1)return route.continue();
      if(++expiredResponses===2)release();
      return route.fulfill({status:403,contentType:'application/json',body:JSON.stringify({error:'页面已过期，请刷新后重试'})});
    });
    try {
      const markdownPromise=page.waitForEvent('download',{predicate:download=>download.suggestedFilename().endsWith('.md')});
      const pdfPromise=page.waitForEvent('download',{predicate:download=>download.suggestedFilename().endsWith('.pdf')});
      await page.click('#export-markdown');await page.click('#export-pdf');
      const [markdown,pdfDownload]=await Promise.all([markdownPromise,pdfPromise]);
      const markdownFile=path.join(output,'session-recovery-notes.md'),pdfFile=path.join(output,'session-recovery-annotated.pdf');
      await markdown.saveAs(markdownFile);await pdfDownload.saveAs(pdfFile);
      assert.match(await fs.readFile(markdownFile,'utf8'),/附近原文/);assert.equal((await fs.readFile(pdfFile)).subarray(0,5).toString(),'%PDF-');
      assert.equal(sessionReads,1);assert.equal(attempts.get('markdown'),2);assert.equal(attempts.get('annotated.pdf'),2);
      assert.equal((await activeRecord()).id,original.id);assert.deepEqual((await activeRecord()).highlights,original.highlights);
    } finally { release();await page.unroute(sessionURL);await page.unroute(exportRoute); }
  });
  await record('session refresh failure keeps pending writes and token recovery replays at most once',async()=>{
    const original=await activeRecord(),highlightURL=base+`/api/documents/${original.id}/highlights`,sessionURL=base+'/api/session';
    let attempts=0,sessionReads=0;
    const observe=request=>{if(request.url()===sessionURL)sessionReads++;};page.on('request',observe);
    await page.route(highlightURL,route=>{attempts++;return route.fulfill({status:403,contentType:'application/json',body:JSON.stringify({error:'页面已过期，请刷新后重试'})});});
    await page.route(sessionURL,route=>route.abort());
    try {
      await dragWord('nearby');await page.locator('#retry-save').waitFor({state:'visible'});
      assert.equal(attempts,1);assert.equal(sessionReads,1);assert.equal(await count(),original.highlights.length);
      assert.equal(await page.locator('.highlight-card').count(),original.highlights.length+1);
      await page.unroute(sessionURL);await page.click('#retry-save');
      await page.waitForFunction(()=>!document.querySelector('#error-banner').hidden&&document.querySelector('#error-text').textContent.includes('页面已过期，请刷新后重试'));
      await page.waitForTimeout(200);assert.equal(attempts,3,'Manual retry sends one request plus at most one replay');assert.equal(sessionReads,2);
      assert.equal(await count(),original.highlights.length);assert.equal(await page.locator('.highlight-card').count(),original.highlights.length+1);
      await page.unroute(highlightURL);await page.click('#retry-save');await saved();
      const restored=await activeRecord();assert.equal(restored.id,original.id);assert.equal(restored.highlights.length,original.highlights.length+1);
      await page.locator(`.highlight-card[data-id="${restored.highlights.at(-1).id}"]`).getByRole('button',{name:'删除',exact:true}).click();await saved();
      assert.deepEqual((await activeRecord()).highlights,original.highlights);
    } finally { await page.unroute(highlightURL);await page.unroute(sessionURL);page.off('request',observe); }
  });
  await record('service restart reloads records from disk',async()=>{
    await setZoom('170%',1.7);await page.locator('#reader-scroll').evaluate(e=>e.scrollTop=450);await page.waitForTimeout(550);await saved();const anchor=await paneAnchor();
    await stopServer();await startServer();await page.goto(base);await saved();assert.equal(await count(),2);assert.equal(await page.inputValue('#page-number'),'2');assert(Math.abs((await paneAnchor()).y-anchor.y)<.003);
    const snapshot=JSON.parse(await fs.readFile(path.join(dataDir,'current-reading.json'),'utf8'));assert.equal(snapshot.highlights.length,2);
    await page.click('#zoom-fit');await zoomRendered('fit');
  });
  if(process.env.PAPER_READER_TEST_PDF)await record('real paper import, text selection, and source integrity',async()=>{
    const filename=process.env.PAPER_READER_TEST_PDF,original=await fs.readFile(filename);await page.setInputFiles('#file-input',filename);await page.locator('#text-layer span').filter({hasText:'Abstract'}).first().waitFor({timeout:30000});await saved();
    const span=page.locator('#text-layer span').filter({hasText:'astronomical'}).first();const fragment=await span.textContent();await dragSpan(fragment);await page.waitForFunction(()=>document.querySelector('#highlight-count').textContent==='1');await saved();assert.equal(await count(),1);const r=await activeRecord();assert(r.highlights[0].rawText.length>10);
    assert.deepEqual(await fs.readFile(filename),original);await page.screenshot({path:path.join(output,'real-paper-private.png')});
  });
  await record('narrow app-pane layout remains usable',async()=>{
    for(const width of [720,535]){
      await page.setViewportSize({width,height:900});await page.locator('#sidebar').waitFor({state:'hidden'});await page.waitForTimeout(250);const pageBox=await page.locator('#pdf-page').boundingBox();assert(pageBox.width<width);assert(await page.locator('#highlight-toggle').isVisible());
      const geometry=await page.evaluate(()=>({height:innerHeight,scrollHeight:document.documentElement.scrollHeight,tools:[...document.querySelectorAll('.zoom-tools > *')].map(e=>({left:e.getBoundingClientRect().left,right:e.getBoundingClientRect().right}))}));
      assert(geometry.scrollHeight<=geometry.height+1,'Toolbar wrapping must not push the reader below the app viewport');assert(geometry.tools.every(r=>r.left>=0&&r.right<=width));
    }
    await page.screenshot({path:path.join(output,'narrow-pane-private.png')});
  });
  assert.deepEqual(consoleErrors,[],'No uncaught browser errors');
  await fs.writeFile(path.join(output,'browser-results.json'),JSON.stringify({results,consoleErrors,dataDir,browserVersion:await browser.version()},null,2));
  console.log(`${results.length} browser checks passed. Artifacts: ${output}`);
} catch(error) {
  if(page)await page.screenshot({path:path.join(output,'failure-private.png')}).catch(()=>{});
  await fs.writeFile(path.join(output,'browser-results.json'),JSON.stringify({results,error:error.stack,consoleErrors,dataDir},null,2));
  console.error(error);process.exitCode=1;
} finally { if(browser)await browser.close();await stopServer(); }
