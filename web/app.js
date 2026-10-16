import { getDocument, GlobalWorkerOptions, TextLayer } from '/vendor/pdfjs/build/pdf.mjs';
import { buildPageText, findMatches } from './search.js';

GlobalWorkerOptions.workerSrc = '/vendor/pdfjs/build/pdf.worker.mjs';
const $ = id => document.getElementById(id);
const colors = {yellow:'#ffe066',green:'#a8dfbe',pink:'#ffb4cc',blue:'#91c9ff',purple:'#c7b4f5',orange:'#ffbe75',red:'#ff9696'};
const lineColors = {yellow:'#b78a00',green:'#308566',pink:'#be4f83',blue:'#276db6',purple:'#7750b7',orange:'#bd6b17',red:'#c33f45'};
const colorLabels = {yellow:'黄色',green:'绿色',pink:'粉色',blue:'蓝色',purple:'紫色',orange:'橙色',red:'红色'};
const styleLabels = {highlight:'高亮',underline:'下划线',strikeout:'删除线'};
let token, current, pdf, pageView, textLayer, textItems = [], pageLabels = [];
let pageNumber = 1, zoom = 'fit', renderSerial = 0, renderTask, undoAction;
let documents = [], pendingSelection, pendingWrites = 0, toastTimer, resizeTimer;
let continuous = true, savingQueue = Promise.resolve(), failedWrites = [];
const MIN_ZOOM = .25, MAX_ZOOM = 4;
let zoomQueue = Promise.resolve(), requestedZoom = 'fit', controlsBusy = false;
let sidebarVisible = window.innerWidth > 950;
let narrowLayout = window.innerWidth <= 950;
let sidebarTab = 'notes', documentSerial = 0, positionTimer, positionDirty = false, pageReady = false;
let searchSerial = 0, searchResults = [], activeSearch = -1, searchQuery = '', searchTruncated = false;
let pageTextCache = new Map(), renderedTextDivs = new Map();
let documentQueue = Promise.resolve();
let sessionRefreshPromise;
const SEARCH_LIMIT = 500;

function status(text, state = '') { $('save-status').textContent = text; $('save-status').className = `save-status ${state}`; }
function error(message, retry = false) { $('error-text').textContent = message; $('error-banner').hidden = false; $('retry-save').hidden = !(retry || failedWrites.length); }
function clearError() { $('error-banner').hidden = true; }
function toast(message) { $('toast').textContent = message; $('toast').hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => $('toast').hidden = true, 3500); }
async function refreshSessionToken(expiredToken) {
  // Another request may have already refreshed while this 403 was in flight.
  if (token && token !== expiredToken) return;
  if (!sessionRefreshPromise) {
    sessionRefreshPromise = (async () => {
      const response = await fetch('/api/session', {method:'GET', mode:'same-origin', cache:'no-store'});
      let session; try { session = await response.json(); } catch {}
      if (!response.ok) throw new Error(session?.error || `操作失败（${response.status}）`);
      if (typeof session?.token !== 'string' || !session.token) throw new Error('无法更新页面会话，请重试');
      // Do not activate a document or replace annotations returned by /session.
      token = session.token;
    })().finally(() => { sessionRefreshPromise = undefined; });
  }
  await sessionRefreshPromise;
}
async function api(path, options = {}) {
  const sentToken = token || '';
  const request = readerToken => fetch(path, { ...options, headers: { 'X-Reader-Token': readerToken, ...options.headers } });
  let response = await request(sentToken);
  if (response.status === 403 && new URL(path, window.location.href).origin === window.location.origin) {
    // Inspect only a clone: callers still need the original successful body.
    let rejection; try { rejection = await response.clone().json(); } catch {}
    if (rejection?.error === '页面已过期，请刷新后重试') {
      await refreshSessionToken(sentToken);
      response = await request(token || ''); // Replay at most once; errors use the existing retry queue.
    }
  }
  if (!response.ok) { let data; try { data = await response.json(); } catch {} throw new Error(data?.error || `操作失败（${response.status}）`); }
  return response;
}
async function json(path, method = 'GET', body) { return (await api(path, { method, ...(body !== undefined ? {body: JSON.stringify(body), headers: {'Content-Type':'application/json'}} : {}) })).json(); }
function enqueueWrite(operation) {
  pendingWrites++; status('正在保存…');
  const result = savingQueue.then(operation);
  savingQueue = result.catch(err => { failedWrites.push(operation); status('保存失败', 'failed'); error(err.message + '。可点击重试保存。', true); }).finally(() => {
    pendingWrites--; if (!pendingWrites && !failedWrites.length) status('已保存到本机', 'saved');
  });
  return result;
}
async function settle() { await savingQueue; if (failedWrites.length) throw new Error('仍有未保存的更改，请先重试保存'); }
function controlsDisabled(disabled) { controlsBusy = disabled; for (const id of ['document-picker','previous-page','next-page','page-number','zoom','zoom-out','zoom-in','zoom-fit','highlight-toggle','highlight-style','highlight-color','copy-all','export-markdown','export-pdf','navigation-toggle','search-toggle','bookmark-toggle','search-submit']) $(id).disabled = disabled; }

function selectedPdfText() {
  const selection = window.getSelection(), layer = $('text-layer');
  if (!selection?.rangeCount || selection.isCollapsed) return '';
  const range = selection.getRangeAt(0);
  return layer.contains(range.startContainer) && layer.contains(range.endContainer) ? selection.toString() : '';
}
function dismissSelectionMenu(clearSelection = false) {
  $('selection-menu').hidden = true; pendingSelection = null;
  if (clearSelection && selectedPdfText()) window.getSelection().removeAllRanges();
}

function zoomLabel(value) {
  if (value === 'fit') return pageView ? `${Number((pageView.viewport.scale * 100).toFixed(1))}%` : '适合宽度';
  return `${Number((value * 100).toFixed(4))}%`;
}
function updateZoomControls() {
  $('zoom').value = zoomLabel(zoom);
  $('zoom-fit').setAttribute('aria-pressed', String(zoom === 'fit'));
  const scale = zoom === 'fit' ? pageView?.viewport.scale : zoom;
  $('zoom-out').disabled = controlsBusy || scale <= MIN_ZOOM;
  $('zoom-in').disabled = controlsBusy || scale >= MAX_ZOOM;
}
function parseZoom(value) {
  const text = value.trim().replace('％', '%');
  if (text === 'fit' || text === '适合宽度') return 'fit';
  if (!/^\d+(?:\.\d+)?%?$/.test(text)) return null;
  const scale = Number(text.replace('%', '')) / 100;
  return Number.isFinite(scale) && scale >= MIN_ZOOM && scale <= MAX_ZOOM ? scale : null;
}
function readingAnchor() {
  const reader = $('reader-scroll'), bounds = reader.getBoundingClientRect(), page = $('pdf-page').getBoundingClientRect();
  return {x:(bounds.left + reader.clientWidth / 2 - page.left) / page.width, y:(bounds.top + reader.clientHeight / 2 - page.top) / page.height};
}
function restoreAnchor(anchor) {
  const reader = $('reader-scroll'), bounds = reader.getBoundingClientRect(), page = $('pdf-page').getBoundingClientRect();
  reader.scrollLeft += page.left + anchor.x * page.width - bounds.left - reader.clientWidth / 2;
  reader.scrollTop += page.top + anchor.y * page.height - bounds.top - reader.clientHeight / 2;
}
function requestZoom(next) {
  if (!pdf || controlsBusy) return zoomQueue;
  if (next === requestedZoom) { $('zoom').value = zoomLabel(next); return zoomQueue; }
  requestedZoom = next; dismissSelectionMenu(true);
  // Queue rapid button presses: each step is retained without overlapping PDF renders.
  zoomQueue = zoomQueue.then(async () => {
    await settle(); const anchor = readingAnchor(); zoom = next;
    await renderPage(); restoreAnchor(anchor); await savePosition();
  }).catch(err => { requestedZoom = zoom; updateZoomControls(); error(err.message); });
  return zoomQueue;
}
function commitZoomInput() {
  const next = parseZoom($('zoom').value);
  if (next === null) { $('zoom').value = zoomLabel(requestedZoom); toast('请输入 25%—400% 的比例，例如 137.5%'); return; }
  requestZoom(next);
}
function stepZoom(direction) {
  const scale = requestedZoom === 'fit' ? pageView.viewport.scale : requestedZoom;
  requestZoom(Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, Math.round((scale + direction * .1) * 1000000) / 1000000)));
}

function renderDocumentPicker() {
  $('document-picker').replaceChildren();
  for (const doc of documents) { const option = document.createElement('option'); option.value = doc.id; option.textContent = doc.name; $('document-picker').append(option); }
  if (current) $('document-picker').value = current.id;
}
function openDocument(docId) {
  controlsDisabled(true); status('正在打开论文…');
  const operation = documentQueue.catch(() => {}).then(() => loadDocument(docId));
  documentQueue = operation;
  return operation;
}
async function loadDocument(docId) {
  controlsDisabled(true);
  let replacingDocument = false;
  try {
    clearTimeout(resizeTimer);
    await zoomQueue; await flushPosition(); await settle(); status('正在打开论文…'); clearError(); dismissSelectionMenu(true);
    replacingDocument = true;
    const generation = ++documentSerial; clearSearch(); pageTextCache = new Map(); pageReady = false;
    if (renderTask) { renderTask.cancel(); try { await renderTask.promise; } catch {} }
    if (textLayer) textLayer.cancel();
    if (pdf) await pdf.destroy();
    pdf = null; pageView = null;
    current = await json(`/api/documents/${docId}/activate`, 'POST', {});
    current.bookmarks ||= [];
    pageNumber = current.position.page; zoom = current.position.zoom; requestedZoom = zoom;
    undoAction = null; $('undo').disabled = true;
    $('document-name').textContent = current.name; $('document-name').title = current.name;
    $('empty-state').hidden = true; $('workspace').hidden = false;
    pdf = await getDocument({url:`/api/documents/${docId}/pdf`, cMapUrl:'/vendor/pdfjs/cmaps/', cMapPacked:true, standardFontDataUrl:'/vendor/pdfjs/standard_fonts/', wasmUrl:'/vendor/pdfjs/wasm/'}).promise;
    pageLabels = await pdf.getPageLabels() || [];
    documents = (await json('/api/session')).documents;
    renderDocumentPicker(); setSidebar(sidebarVisible); renderList(); renderBookmarks();
    $('outline-list').replaceChildren(); $('outline-status').textContent = '正在读取目录…';
    await renderPage();
    if (current.position.anchor) restoreAnchor(current.position.anchor);
    else { $('reader-scroll').scrollTop = 0; $('reader-scroll').scrollLeft = 0; }
    status('已保存到本机', 'saved');
    loadOutline(pdf, generation).catch(err => { if (generation === documentSerial) $('outline-status').textContent = `目录读取失败：${err.message}`; });
  } catch (err) {
    if (replacingDocument) {
      pageReady = false; pdf = null; pageView = null;
      $('workspace').hidden = true; $('empty-state').hidden = false;
    }
    status(failedWrites.length ? '保存失败' : '打开未完成', 'failed');
    throw err;
  } finally {
    controlsDisabled(false);
    if (pdf && pageReady) updatePageControls();
  }
}

function updatePageControls() {
  $('page-number').value = pageNumber; $('page-number').max = pdf.numPages;
  $('page-count').textContent = `/ ${pdf.numPages}`;
  $('previous-page').disabled = pageNumber === 1; $('next-page').disabled = pageNumber === pdf.numPages;
  updateZoomControls();
  updateBookmarkButton();
  $('page-label').textContent = `PDF 第 ${pageNumber} 页` + (pageLabels[pageNumber - 1] ? ` · 页标签 ${pageLabels[pageNumber - 1]}` : '');
}
async function renderPage() {
  if (!pdf) return;
  const serial = ++renderSerial;
  pageReady = false;
  $('page-loading').hidden = false; dismissSelectionMenu(true);
  if (renderTask) { renderTask.cancel(); try { await renderTask.promise; } catch {} }
  if (textLayer) textLayer.cancel();
  const page = await pdf.getPage(pageNumber);
  if (serial !== renderSerial) return;
  const base = page.getViewport({scale:1});
  const available = $('reader-scroll').clientWidth - (window.innerWidth < 570 ? 24 : window.innerWidth < 950 ? 36 : 48);
  const scale = zoom === 'fit' ? Math.max(.25, Math.min(1.75, available / base.width)) : Number(zoom);
  const viewport = page.getViewport({scale});
  pageView = {page, viewport, number:pageNumber};
  const element = $('pdf-page'); element.style.width = `${viewport.width}px`; element.style.height = `${viewport.height}px`;
  element.style.setProperty('--scale-factor', scale); element.style.setProperty('--total-scale-factor', scale * (page.userUnit || 1));
  element.style.setProperty('--user-unit', page.userUnit || 1);
  const canvas = $('pdf-canvas'), ratio = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.floor(viewport.width * ratio); canvas.height = Math.floor(viewport.height * ratio);
  canvas.style.width = `${viewport.width}px`; canvas.style.height = `${viewport.height}px`;
  $('text-layer').replaceChildren(); $('highlight-layer').replaceChildren(); $('search-layer').replaceChildren();
  renderTask = page.render({canvasContext:canvas.getContext('2d'), viewport, transform:ratio === 1 ? null : [ratio,0,0,ratio,0,0]});
  const content = await page.getTextContent();
  if (serial !== renderSerial) return;
  textItems = content.items;
  textLayer = new TextLayer({textContentSource:content, container:$('text-layer'), viewport});
  await Promise.all([renderTask.promise, textLayer.render()]);
  if (serial !== renderSerial) return;
  $('no-text').hidden = content.items.some(item => item.str?.trim());
  // TextLayer allocates one textDiv per string item, including empty text runs.
  renderedTextDivs = new Map(); let textIndex = 0;
  content.items.forEach((item, index) => { if (typeof item.str === 'string') renderedTextDivs.set(index, textLayer.textDivs[textIndex++]); });
  pageTextCache.set(pageNumber, buildPageText(content.items));
  paintHighlights(); paintSearchResults(); updatePageControls(); renderList(); $('page-loading').hidden = true;
  element.dataset.zoom = String(zoom);
  pageReady = true;
}

function paintHighlights(focusedId) {
  if (!pageView || !current) return;
  $('highlight-layer').replaceChildren();
  for (const h of current.highlights.filter(h => h.page === pageView.number)) {
    for (const quad of h.quads) {
      const points = [];
      for (let i=0;i<8;i+=2) points.push(pageView.viewport.convertToViewportPoint(quad[i],quad[i+1]));
      const xs = points.map(p=>p[0]), ys=points.map(p=>p[1]);
      const style = h.style || 'highlight';
      const rect = document.createElement('div'); rect.className = `highlight-rect annotation-${style}` + (h.id === focusedId ? ' focused' : '');
      rect.dataset.highlightId = h.id;
      rect.dataset.style = style; rect.dataset.color = h.color;
      Object.assign(rect.style, {left:`${Math.min(...xs)}px`,top:`${Math.min(...ys)}px`,width:`${Math.max(...xs)-Math.min(...xs)}px`,height:`${Math.max(...ys)-Math.min(...ys)}px`,backgroundColor:style==='highlight'?colors[h.color]:'transparent'});
      rect.style.setProperty('--mark-color',lineColors[h.color]);
      rect.style.setProperty('--mark-width',`${Math.max(1,pageView.viewport.scale*.85)}px`);
      $('highlight-layer').append(rect);
    }
  }
}

function captureSelection() {
  if (!pageReady || controlsBusy) return null;
  const selection = window.getSelection();
  if (!selection?.rangeCount || selection.isCollapsed || !pageView) return null;
  const range = selection.getRangeAt(0), layer = $('text-layer');
  if (!layer.contains(range.startContainer) || !layer.contains(range.endContainer)) return null;
  const rawText = selection.toString(); if (!rawText.trim()) return null;
  const pageBounds = $('pdf-page').getBoundingClientRect();
  // DOM selection geometry is transformed back to PDF coordinates, independent of zoom.
  const rectangles = [...range.getClientRects()].filter(r => r.width > 1 && r.height > 1 && r.left >= pageBounds.left-2 && r.right <= pageBounds.right+2);
  const unique = rectangles.filter((r,i) => !rectangles.slice(0,i).some(other => Math.abs(other.x-r.x)<.5 && Math.abs(other.y-r.y)<.5 && Math.abs(other.width-r.width)<.5 && Math.abs(other.height-r.height)<.5));
  const quads = unique.map(r => [
    ...pageView.viewport.convertToPdfPoint(r.left-pageBounds.left,r.top-pageBounds.top),
    ...pageView.viewport.convertToPdfPoint(r.right-pageBounds.left,r.top-pageBounds.top),
    ...pageView.viewport.convertToPdfPoint(r.left-pageBounds.left,r.bottom-pageBounds.top),
    ...pageView.viewport.convertToPdfPoint(r.right-pageBounds.left,r.bottom-pageBounds.top)
  ]);
  if (!quads.length) return null;
  const spans = [...layer.querySelectorAll('span')].filter(span => span.firstChild?.nodeType === Node.TEXT_NODE);
  const start = range.startContainer.nodeType === Node.TEXT_NODE ? range.startContainer.parentElement : range.startContainer;
  const end = range.endContainer.nodeType === Node.TEXT_NODE ? range.endContainer.parentElement : range.endContainer;
  const startIndex = spans.indexOf(start.closest('span')), endIndex = spans.indexOf(end.closest('span'));
  const before = spans.slice(Math.max(0,startIndex-8),Math.max(0,startIndex)).map(s=>s.textContent).join(' ');
  const after = spans.slice(endIndex+1,endIndex+9).map(s=>s.textContent).join(' ');
  // Preserve the unselected prefix/suffix of the same text run so a marked word retains its sentence.
  const prefix = range.startContainer.nodeType === Node.TEXT_NODE ? range.startContainer.textContent.slice(0,range.startOffset) : '';
  const suffix = range.endContainer.nodeType === Node.TEXT_NODE ? range.endContainer.textContent.slice(range.endOffset) : '';
  return {clientId:crypto.randomUUID().replaceAll('-',''),page:pageView.number,pageLabel:pageLabels[pageView.number-1] || String(pageView.number),rawText,quads,textOrder:Math.max(0,startIndex),color:$('highlight-color').value,style:$('highlight-style').value,contextBefore:before+(before?' ':'')+prefix,contextAfter:suffix+(after?' ':'')+after};
}
function rememberUndo(action) { undoAction = action; $('undo').disabled = false; }
async function addSelection(selection) {
  if (!selection || !current) return;
  const docId=current.id;
  const temporary={...selection,id:'pending-'+selection.clientId,text:selection.rawText,kind:'passage',note:''};
  current.highlights.push(temporary); paintHighlights(); renderList();
  dismissSelectionMenu(true);
  const operation=async()=>{
    const added=await json(`/api/documents/${docId}/highlights`,'POST',selection);
    if(current?.id===docId){ const index=current.highlights.findIndex(h=>h.id===temporary.id); if(index>=0)current.highlights[index]=added; else current.highlights.push(added); paintHighlights(); renderList(); rememberUndo({type:'add',id:added.id,docId}); }
    return added;
  };
  try { await enqueueWrite(operation); } catch { /* Visible retry retains the selection. */ }
}

async function deleteHighlight(h) {
  if(h.id.startsWith('pending-'))return;
  const docId=current.id;
  await enqueueWrite(async()=>{await json(`/api/documents/${docId}/highlights/${h.id}`,'DELETE'); if(current?.id===docId){current.highlights=current.highlights.filter(item=>item.id!==h.id);paintHighlights();renderList();rememberUndo({type:'delete',item:h,docId});}});
}
async function updateHighlight(h, body) {
  if(h.id.startsWith('pending-'))return;
  const docId=current.id;
  await enqueueWrite(async()=>{const item=await json(`/api/documents/${docId}/highlights/${h.id}`,'PATCH',body); if(current?.id===docId){Object.assign(h,item);paintHighlights();renderList();}});
}
function button(label, action, className='') { const b=document.createElement('button');b.textContent=label;b.className=className;b.addEventListener('click',()=>Promise.resolve(action()).catch(err=>error(err.message,true)));return b; }
function passageText(h) { return `论文：${current.name}\nPDF 第 ${h.page} 页（页标签 ${h.pageLabel}）\n标注：${styleLabels[h.style||'highlight']} · ${colorLabels[h.color]}\n标注原文：${h.rawText}\n附近原文（请回看PDF核对）：\n${h.contextBefore}【标注】${h.rawText}【标注结束】${h.contextAfter}\n\n请找到完整句子，先给准确翻译，再拆短语、主干和修饰关系，结合上下文解释。删除线只是读者标记，不代表原文错误。`; }
function markPicker(labels,value,label,field,h) {
  const select=document.createElement('select');select.setAttribute('aria-label',label);select.disabled=h.id.startsWith('pending-');
  for(const [key,text] of Object.entries(labels)){const option=document.createElement('option');option.value=key;option.textContent=text;select.append(option);}
  select.value=value;select.addEventListener('change',()=>updateHighlight(h,{[field]:select.value}).catch(err=>{select.value=value;error(err.message,true);}));return select;
}
function renderList() {
  if(!current)return;
  $('highlight-count').textContent=current.highlights.length;
  const list=$('highlight-list');list.replaceChildren();
  const filter=$('highlight-filter').value;
  const items=current.highlights.filter(h=>filter==='all'||(filter==='page'&&h.page===pageNumber)||(filter==='vocabulary'&&h.kind==='vocabulary'));
  items.sort((a,b)=>a.page-b.page||(a.textOrder||0)-(b.textOrder||0));
  if(!items.length){const empty=document.createElement('div');empty.className='list-empty';empty.textContent=filter==='vocabulary'?'还没有确认的生词。':'在论文里选中一段文字，\n第一个阅读卡点就会留在这里。';list.append(empty);}
  for(const h of items){
    const card=document.createElement('article');card.className=`highlight-card ${h.color}`;card.dataset.id=h.id;card.style.setProperty('--mark-color',lineColors[h.color]);
    const top=document.createElement('div');top.className='card-top';
    top.append(button(`第 ${h.page} 页`,async()=>{await navigate(h.page);paintHighlights(h.id);const r=$('highlight-layer').querySelector(`[data-highlight-id="${h.id}"]`);r?.scrollIntoView({block:'center',behavior:'smooth'});},'page-link'));
    const kind=document.createElement('span');kind.textContent=h.id.startsWith('pending-')?'待保存':h.kind==='vocabulary'?'确认的生词':'整句卡点';top.append(kind);
    const text=document.createElement('p');text.className='card-text';text.textContent=h.text;
    const marks=document.createElement('div');marks.className='card-mark-controls';
    marks.append(markPicker(styleLabels,h.style||'highlight','此标注方式','style',h),markPicker(colorLabels,h.color,'此标注颜色','color',h));
    const actions=document.createElement('div');actions.className='card-actions';
    actions.append(button('复制',()=>copy(passageText(h))),button(h.kind==='vocabulary'?'改为卡点':'收为生词',()=>updateHighlight(h,{kind:h.kind==='vocabulary'?'passage':'vocabulary'})),button('删除',()=>deleteHighlight(h)));
    const details=document.createElement('details');const summary=document.createElement('summary');summary.textContent=h.note?'查看讲解／笔记':'补充讲解／笔记（可选）';
    const note=document.createElement('textarea');note.value=h.note;note.setAttribute('aria-label','讲解或笔记');note.placeholder='可以把聊天中确认过的解释粘贴在这里。';
    details.append(summary,note,button('保存笔记',async()=>{await updateHighlight(h,{note:note.value});toast('笔记已保存');},'note-save'));
    card.append(top,text,marks,actions,details);list.append(card);
  }
}

function navigate(number, destination) {
  if (!pdf || controlsBusy) return Promise.resolve();
  const next = Math.max(1, Math.min(pdf.numPages, Math.trunc(Number(number)) || pageNumber));
  const generation = documentSerial;
  zoomQueue = zoomQueue.then(async () => {
    if (generation !== documentSerial) return;
    await flushPosition(); await settle(); pageNumber = next;
    $('reader-scroll').scrollTop = 0; $('reader-scroll').scrollLeft = 0;
    await renderPage();
    if (destination && Number.isFinite(destination.top)) {
      const [x, y] = pageView.viewport.convertToViewportPoint(destination.left ?? pageView.page.view[0], destination.top);
      const bounds = $('reader-scroll').getBoundingClientRect(), page = $('pdf-page').getBoundingClientRect();
      $('reader-scroll').scrollTop += page.top + y - bounds.top - 18;
      if (Number.isFinite(destination.left)) $('reader-scroll').scrollLeft += page.left + x - bounds.left - 18;
    }
    await savePosition();
  }).catch(err => error(err.message));
  return zoomQueue;
}
function positionSnapshot() {
  const anchor = readingAnchor();
  return {page:pageNumber, zoom, anchor:{x:Math.max(0,Math.min(1,anchor.x)), y:Math.max(0,Math.min(1,anchor.y))}};
}
async function savePosition() {
  if (!current || !pageReady) return;
  clearTimeout(positionTimer); positionDirty = false;
  const docId = current.id, position = positionSnapshot();
  await enqueueWrite(async () => {
    const saved = await json(`/api/documents/${docId}/position`, 'PUT', position);
    if (current?.id === docId) current.position = saved;
  });
}
async function flushPosition() { if (positionDirty && pageReady) await savePosition(); }
function rerenderAtAnchor(anchor = readingAnchor()) {
  const generation = documentSerial, anchorPage = pageNumber;
  zoomQueue = zoomQueue.then(async () => {
    if (generation !== documentSerial || zoom !== 'fit') return;
    const effectiveAnchor = anchorPage === pageNumber ? anchor : readingAnchor();
    await settle(); await renderPage();
    if (generation === documentSerial) restoreAnchor(effectiveAnchor);
  }).catch(err => error(err.message));
  return zoomQueue;
}
function setSidebar(visible){sidebarVisible=visible;$('sidebar').hidden=!visible;$('reader-layout').classList.toggle('sidebar-hidden',!visible);$('sidebar-toggle').setAttribute('aria-expanded',String(visible));}
function setSidebarTab(tab) {
  sidebarTab = tab;
  for (const name of ['notes','navigation','search']) {
    $(`${name}-panel`).hidden = name !== tab;
    $(`${name}-tab`).setAttribute('aria-selected', String(name === tab));
    $(`${name}-tab`).tabIndex = name === tab ? 0 : -1;
  }
  $('sidebar-title').textContent = {notes:'留下的卡点',navigation:'目录与书签',search:'全文搜索'}[tab];
}
async function showSidebar(tab, visible = true) {
  const anchor = pdf && pageReady ? readingAnchor() : null;
  setSidebarTab(tab); setSidebar(visible);
  if (pdf && zoom === 'fit' && anchor) await rerenderAtAnchor(anchor);
}

function updateBookmarkButton() {
  const marked = current?.bookmarks.some(item => item.page === pageNumber);
  $('bookmark-toggle').textContent = marked ? '★ 书签' : '☆ 书签';
  $('bookmark-toggle').setAttribute('aria-pressed', String(Boolean(marked)));
  $('bookmark-toggle').title = marked ? '取消当前页书签' : '收藏当前页';
}
async function putBookmark(page, title) {
  if (!current || controlsBusy) return;
  const docId = current.id;
  await enqueueWrite(async () => {
    const item = await json(`/api/documents/${docId}/bookmarks/${page}`, 'PUT', {title});
    if (current?.id !== docId) return;
    current.bookmarks = current.bookmarks.filter(bookmark => bookmark.page !== page).concat(item).sort((a,b) => a.page-b.page);
    renderBookmarks(); updateBookmarkButton();
  });
}
async function removeBookmark(page) {
  if (!current || controlsBusy) return;
  const docId = current.id;
  await enqueueWrite(async () => {
    await json(`/api/documents/${docId}/bookmarks/${page}`, 'DELETE');
    if (current?.id !== docId) return;
    current.bookmarks = current.bookmarks.filter(item => item.page !== page);
    renderBookmarks(); updateBookmarkButton();
  });
}
function renderBookmarks() {
  const list = $('bookmark-list'); list.replaceChildren();
  if (!current.bookmarks.length) { const empty = document.createElement('p'); empty.className = 'sidebar-hint'; empty.textContent = '还没有书签。'; list.append(empty); }
  for (const item of current.bookmarks) {
    const card = document.createElement('article'); card.className = 'bookmark-card'; card.dataset.page = item.page;
    const actions = document.createElement('div');
    actions.append(button(`第 ${item.page} 页`, async () => { if (narrowLayout) setSidebar(false); await navigate(item.page); }, 'page-link'), button('删除', () => removeBookmark(item.page)));
    const title = document.createElement('input'); title.value = item.title; title.maxLength = 200; title.required = true; title.setAttribute('aria-label', `第 ${item.page} 页书签名称`);
    title.addEventListener('input', () => title.setCustomValidity(''));
    card.append(actions, title, button('保存名称', async () => {
      title.setCustomValidity(title.value.trim() ? '' : '请输入书签名称');
      if (!title.reportValidity()) return;
      await putBookmark(item.page, title.value); toast('书签名称已保存');
    }));
    list.append(card);
  }
}
async function loadOutline(documentPdf, generation) {
  const outline = await documentPdf.getOutline();
  if (generation !== documentSerial) return;
  if (!outline?.length) { $('outline-status').textContent = '这份 PDF 没有内置目录。可以用页面书签记录重要位置。'; return; }
  let count = 0;
  async function tree(items, depth = 0) {
    const list = document.createElement('ul');
    for (const item of items) {
      if (generation !== documentSerial || count >= 1000 || depth > 12) break;
      count++;
      const entry = document.createElement('li');
      let target;
      try {
        const dest = typeof item.dest === 'string' ? await documentPdf.getDestination(item.dest) : item.dest;
        if (Array.isArray(dest)) {
          const index = Number.isInteger(dest[0]) ? dest[0] : await documentPdf.getPageIndex(dest[0]);
          if (index >= 0 && index < documentPdf.numPages) {
            const type = dest[1]?.name;
            target = {page:index+1, ...(type === 'XYZ' ? {left:dest[2],top:dest[3]} : ['FitH','FitBH'].includes(type) ? {top:dest[2]} : {})};
          }
        }
      } catch { /* Unresolved or external destinations are not opened as arbitrary URLs. */ }
      const link = button(item.title || '未命名章节', async () => { if (narrowLayout) setSidebar(false); await navigate(target.page, target); });
      link.disabled = !target; if (target) link.dataset.page = target.page;
      else link.title = '此目录项没有可用的页内目标';
      entry.append(link);
      if (item.items?.length) {
        const details = document.createElement('details'); details.open = depth === 0;
        const summary = document.createElement('summary'); summary.textContent = '子章节';
        details.append(summary, await tree(item.items, depth+1)); entry.append(details);
      }
      list.append(entry);
    }
    return list;
  }
  const list = await tree(outline);
  if (generation !== documentSerial) return;
  $('outline-list').replaceChildren(list);
  $('outline-status').textContent = `来自 PDF 的内置目录${count >= 1000 ? '（最多展示 1000 项）' : ''}；点击可跳转。`;
}

function clearSearch() {
  searchSerial++; searchResults = []; activeSearch = -1; searchQuery = ''; searchTruncated = false;
  $('search-input').value = ''; $('search-results').replaceChildren(); $('search-layer').replaceChildren();
  $('search-status').textContent = '搜索带文本层的页面；不支持扫描件 OCR。'; $('search-status').dataset.state = 'empty';
  updateSearchControls();
}
function updateSearchControls() {
  $('search-previous').disabled = !searchResults.length; $('search-next').disabled = !searchResults.length;
  $('search-results').dataset.count = searchResults.length;
}
function searchSummary() {
  return searchResults.length ? `${activeSearch >= 0 ? `第 ${activeSearch+1} / ` : '找到 '}${searchResults.length} 处${searchTruncated ? '（仅显示前 500 处，请缩小关键词范围）' : ''}` : '没有找到匹配文字。扫描页或 PDF 文本顺序可能影响搜索。';
}
function renderSearchList() {
  const list = $('search-results'); list.replaceChildren();
  const serial = searchSerial;
  searchResults.forEach((item, index) => {
    const result = button('', () => { if (serial === searchSerial) return showSearchMatch(index); }, 'search-result');
    result.dataset.index = index; result.setAttribute('aria-current', String(index === activeSearch));
    const label = document.createElement('small'); label.textContent = `第 ${item.page} 页 · 结果 ${index+1}`;
    const snippet = document.createElement('span'); snippet.textContent = item.snippet;
    result.append(label, snippet); list.append(result);
  });
  updateSearchControls();
}
async function runSearch() {
  if (!pdf || controlsBusy) return;
  const query = $('search-input').value.trim(); clearSearch(); $('search-input').value = query;
  if (!query) return;
  searchQuery = query;
  const serial = searchSerial, generation = documentSerial, documentPdf = pdf;
  let textPages = 0;
  $('search-status').dataset.state = 'searching';
  try {
    for (let number = 1; number <= documentPdf.numPages; number++) {
      if (serial !== searchSerial || generation !== documentSerial) return;
      $('search-status').textContent = `正在搜索第 ${number} / ${documentPdf.numPages} 页…`;
      let text = pageTextCache.get(number);
      if (!text) { const page = await documentPdf.getPage(number); text = buildPageText((await page.getTextContent()).items); }
      if (serial !== searchSerial || generation !== documentSerial) return;
      pageTextCache.set(number, text); if (text.text.trim()) textPages++;
      const matches = findMatches(text, query, {limit:SEARCH_LIMIT-searchResults.length});
      searchResults.push(...matches.map(match => ({...match,page:number})));
      if (searchResults.length >= SEARCH_LIMIT) { searchTruncated = true; break; }
    }
    if (serial !== searchSerial || generation !== documentSerial) return;
    renderSearchList(); paintSearchResults();
    $('search-status').dataset.state = 'ready';
    $('search-status').textContent = textPages ? searchSummary() : '这份 PDF 没有可搜索的文本层，暂不支持扫描件 OCR。';
  } catch (err) { if (serial === searchSerial) { $('search-status').dataset.state = 'failed'; $('search-status').textContent = `搜索未完成：${err.message}`; } }
}
function paintSearchResults() {
  $('search-layer').replaceChildren(); if (!pageView) return;
  const pageBounds = $('pdf-page').getBoundingClientRect();
  searchResults.forEach((item, index) => {
    if (item.page !== pageView.number) return;
    for (const part of item.parts) {
      const node = renderedTextDivs.get(part.itemIndex)?.firstChild;
      if (!node || node.nodeType !== Node.TEXT_NODE || part.end > node.textContent.length) continue;
      const range = document.createRange(); range.setStart(node, part.start); range.setEnd(node, part.end);
      for (const rect of range.getClientRects()) {
        if (rect.width < .1 || rect.height < .1) continue;
        const mark = document.createElement('div'); mark.className = 'search-rect' + (index === activeSearch ? ' current' : ''); mark.dataset.index = index;
        Object.assign(mark.style, {left:`${rect.left-pageBounds.left}px`,top:`${rect.top-pageBounds.top}px`,width:`${rect.width}px`,height:`${rect.height}px`});
        $('search-layer').append(mark);
      }
    }
  });
}
async function showSearchMatch(index) {
  if (!searchResults.length) return;
  const serial = searchSerial;
  activeSearch = (index+searchResults.length) % searchResults.length;
  const selected = activeSearch, item = searchResults[selected];
  if (narrowLayout) setSidebar(false);
  await navigate(item.page);
  if (serial !== searchSerial || selected !== activeSearch) return;
  paintSearchResults(); renderSearchList(); $('search-status').textContent = searchSummary();
  $('search-layer').querySelector('.current')?.scrollIntoView({block:'center',inline:'nearest'});
  await savePosition();
}
async function copy(text){try{await navigator.clipboard.writeText(text);toast('已复制，回到聊天粘贴即可');}catch{error('剪贴板暂不可用，请使用 Markdown 导出');}}
async function download(operation){await settle();const response=await api(`/api/documents/${current.id}/${operation}`);const blob=await response.blob();const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=current.name.replace(/\.pdf$/i,'')+(operation==='markdown'?'.md':'-annotated.pdf');a.click();setTimeout(()=>URL.revokeObjectURL(url),5000);toast(operation==='markdown'?'已导出笔记，可在 Obsidian 中打开':'已导出批注副本，原 PDF 保持不变');}
async function importFile(file){if(!file)return;await settle();status('正在导入…');try{const result=await (await api('/api/import',{method:'POST',headers:{'X-Filename':encodeURIComponent(file.name),'Content-Type':'application/pdf'},body:file})).json();await openDocument(result.id);}catch(err){error(err.message);status('导入未完成','failed');}finally{$('file-input').value='';}}

$('file-input').addEventListener('change',event=>importFile(event.target.files[0]));
for(const id of ['open-file','empty-open'])$(id).addEventListener('click',()=>$('file-input').click());
$('open-demo').addEventListener('click',async()=>{try{const bytes=await(await fetch('/examples/reader-demo.pdf')).blob();await importFile(new File([bytes],'Paper Reader Demo.pdf',{type:'application/pdf'}));}catch(err){error(err.message);}});
$('document-picker').addEventListener('change',event=>openDocument(event.target.value).catch(err=>error(err.message)));
$('previous-page').addEventListener('click',()=>navigate(pageNumber-1).catch(err=>error(err.message)));
$('next-page').addEventListener('click',()=>navigate(pageNumber+1).catch(err=>error(err.message)));
$('page-number').addEventListener('change',event=>navigate(event.target.value).catch(err=>error(err.message)));
$('zoom').addEventListener('change',commitZoomInput);
$('zoom').addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();commitZoomInput();}});
$('zoom-out').addEventListener('click',()=>stepZoom(-1));
$('zoom-in').addEventListener('click',()=>stepZoom(1));
$('zoom-fit').addEventListener('click',()=>requestZoom('fit'));
function updateMarkTools() {
  const style=$('highlight-style').value;
  $('highlight-selection').textContent=style==='highlight'?'标记这段':`添加${styleLabels[style]}`;
  $('highlight-color').style.borderLeftColor=lineColors[$('highlight-color').value];
  $('highlight-toggle').textContent=continuous?'▰ 连续标记':'▱ 选文模式';
}
$('highlight-style').addEventListener('change',updateMarkTools);
$('highlight-color').addEventListener('change',updateMarkTools);
$('highlight-toggle').addEventListener('click',()=>{dismissSelectionMenu(true);continuous=!continuous;$('highlight-toggle').classList.toggle('active',continuous);$('highlight-toggle').setAttribute('aria-pressed',String(continuous));updateMarkTools();toast(continuous?'连续标记已开启，选中文字会按当前样式保存':'选文后可复制，或点击菜单添加标注');});
$('text-layer').addEventListener('pointerup',event=>{if(event.button!==0)return;setTimeout(()=>{const selected=captureSelection();if(!selected){dismissSelectionMenu();return;}if(continuous){addSelection(selected);}else{pendingSelection=selected;const menu=$('selection-menu');menu.hidden=false;menu.style.left=`${Math.max(5,Math.min(event.clientX,window.innerWidth-menu.offsetWidth-5))}px`;menu.style.top=`${Math.max(5,Math.min(event.clientY+15,window.innerHeight-menu.offsetHeight-5))}px`;}},0);});
// The menu is valid only while its PDF selection still exists. Never retain a canceled range.
document.addEventListener('selectionchange',()=>{if(pendingSelection&&selectedPdfText()!==pendingSelection.rawText)dismissSelectionMenu();});
document.addEventListener('pointerdown',event=>{if(!event.target.closest('#selection-menu, #highlight-color, #highlight-style'))dismissSelectionMenu();},true);
document.addEventListener('scroll',()=>dismissSelectionMenu(),{capture:true,passive:true});
window.addEventListener('blur',()=>dismissSelectionMenu());
document.addEventListener('pointercancel',()=>dismissSelectionMenu());
$('selection-menu').addEventListener('pointerdown',event=>event.preventDefault());
$('highlight-selection').addEventListener('click',()=>addSelection(pendingSelection ? {...pendingSelection,color:$('highlight-color').value,style:$('highlight-style').value} : null));
$('copy-selection').addEventListener('click',()=>{if(pendingSelection)copy(pendingSelection.rawText);dismissSelectionMenu(true);});
$('cancel-selection').addEventListener('click',()=>dismissSelectionMenu(true));
$('sidebar-toggle').addEventListener('click',()=>showSidebar('notes',!sidebarVisible||sidebarTab!=='notes').catch(err=>error(err.message)));
$('sidebar-close').addEventListener('click',()=>showSidebar(sidebarTab,false).catch(err=>error(err.message)));
for (const tab of ['notes','navigation','search']) {
  $(`${tab}-tab`).addEventListener('click',()=>setSidebarTab(tab));
  $(`${tab}-tab`).addEventListener('keydown', event => {
    if (!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
    event.preventDefault(); const tabs = ['notes','navigation','search'], index = tabs.indexOf(sidebarTab);
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? 2 : (index+(event.key === 'ArrowRight' ? 1 : 2))%3;
    setSidebarTab(tabs[next]); $(`${tabs[next]}-tab`).focus();
  });
}
$('navigation-toggle').addEventListener('click',()=>showSidebar('navigation').catch(err=>error(err.message)));
async function openSearch() { await showSidebar('search'); $('search-input').focus(); $('search-input').select(); }
$('search-toggle').addEventListener('click',()=>openSearch().catch(err=>error(err.message)));
$('search-form').addEventListener('submit',event=>{event.preventDefault();runSearch();});
$('search-input').addEventListener('keydown',event=>{
  if(event.key==='Enter'&&searchResults.length&&$('search-input').value.trim()===searchQuery){event.preventDefault();showSearchMatch(event.shiftKey&&activeSearch<0?searchResults.length-1:activeSearch+(event.shiftKey?-1:1)).catch(err=>error(err.message));}
});
$('search-next').addEventListener('click',()=>showSearchMatch(activeSearch+1).catch(err=>error(err.message)));
$('search-previous').addEventListener('click',()=>showSearchMatch(activeSearch<0?searchResults.length-1:activeSearch-1).catch(err=>error(err.message)));
$('search-clear').addEventListener('click',()=>{clearSearch();$('search-input').focus();});
$('bookmark-toggle').addEventListener('click',async()=>{
  if(!current||controlsBusy)return;const page=pageNumber;
  $('bookmark-toggle').disabled=true;
  try { await settle(); if(current.bookmarks.some(item=>item.page===page))await removeBookmark(page);else await putBookmark(page,`第 ${page} 页`); }
  catch(err){error(err.message,true);} finally{$('bookmark-toggle').disabled=false;}
});
$('reader-scroll').addEventListener('scroll',()=>{
  if(!current||!pageReady||controlsBusy)return;
  positionDirty=true;clearTimeout(positionTimer);
  positionTimer=setTimeout(()=>flushPosition().catch(()=>{}),400);
},{passive:true});
$('highlight-filter').addEventListener('change',renderList);
$('copy-all').addEventListener('click',async()=>{try{await settle();const text=await(await api(`/api/documents/${current.id}/markdown`)).text();await copy(text);}catch(err){error(err.message);}});
for(const [id,operation] of [['export-markdown','markdown'],['export-pdf','annotated.pdf']])$(id).addEventListener('click',()=>download(operation).catch(err=>error(err.message)));
$('help-toggle').addEventListener('click',()=>$('help').hidden=!$('help').hidden);
$('dismiss-error').addEventListener('click',clearError);
$('retry-save').addEventListener('click',async()=>{const operations=failedWrites.splice(0);clearError();for(let i=0;i<operations.length;i++){try{await enqueueWrite(operations[i]);}catch{failedWrites.push(...operations.slice(i+1));break;}}});
$('undo').addEventListener('click',async()=>{try{await settle();const action=undoAction;if(!action||action.docId!==current.id)return;undoAction=null;$('undo').disabled=true;if(action.type==='add'){await enqueueWrite(async()=>{await json(`/api/documents/${current.id}/highlights/${action.id}`,'DELETE');current.highlights=current.highlights.filter(h=>h.id!==action.id);paintHighlights();renderList();});}else{const restored=await enqueueWrite(()=>json(`/api/documents/${current.id}/highlights`,'POST',action.item));if(action.item.note||action.item.kind==='vocabulary')Object.assign(restored,await json(`/api/documents/${current.id}/highlights/${restored.id}`,'PATCH',{note:action.item.note,kind:action.item.kind}));current.highlights.push(restored);paintHighlights();renderList();}toast('已撤销');}catch(err){error(err.message,true);}});
document.addEventListener('keydown',event=>{
  if(event.key==='Escape'){dismissSelectionMenu(true);if(event.target===$('zoom'))updateZoomControls();if(sidebarTab==='search'&&sidebarVisible)showSidebar('search',false).catch(err=>error(err.message));return;}
  const editing=event.target.isContentEditable||/INPUT|TEXTAREA|SELECT/.test(event.target.tagName);
  if((event.metaKey||event.ctrlKey)&&event.key.toLowerCase()==='f'&&pdf&&!controlsBusy){event.preventDefault();event.stopPropagation();openSearch().catch(err=>error(err.message));return;}
  if((event.metaKey||event.ctrlKey)&&pdf&&(!editing||event.target===$('zoom'))){
    if(['+','=','-','0'].includes(event.key)){event.preventDefault();event.stopPropagation();if(!controlsBusy){if(event.key==='0')requestZoom('fit');else stepZoom(event.key==='-'?-1:1);}return;}
    if(event.key==='z'&&!editing){event.preventDefault();$('undo').click();}
  }
},true);
window.addEventListener('resize',()=>{dismissSelectionMenu();clearTimeout(resizeTimer);const anchor=pdf&&pageReady?readingAnchor():null,generation=documentSerial;resizeTimer=setTimeout(()=>{if(generation!==documentSerial)return;const nowNarrow=window.innerWidth<=950;if(nowNarrow&&!narrowLayout&&sidebarVisible)setSidebar(false);narrowLayout=nowNarrow;if(pdf&&zoom==='fit'&&anchor)rerenderAtAnchor(anchor).catch(err=>error(err.message));},180);});
// A final small position write can outlive a closing tab. Annotation writes still use the visible retry queue.
window.addEventListener('pagehide',()=>{
  if(current&&pageReady)fetch(`/api/documents/${current.id}/position`,{method:'PUT',headers:{'X-Reader-Token':token,'Content-Type':'application/json'},body:JSON.stringify(positionSnapshot()),keepalive:true}).catch(()=>{});
});
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='hidden')flushPosition().catch(()=>{});});
window.addEventListener('beforeunload',event=>{if(pendingWrites||failedWrites.length){event.preventDefault();event.returnValue='';}});

async function boot(){
  updateMarkTools();
  const session=await json('/api/session');token=session.token;documents=session.documents;
  if(session.activeId){await openDocument(session.activeId);}else{$('empty-state').hidden=false;status('本机工作空间','saved');for(const doc of documents)$('recent-documents').append(button(doc.name,()=>openDocument(doc.id)));}
}
boot().catch(err=>{error(err.message+'。请确认本机服务正在运行，再刷新页面。');status('连接未完成','failed');$('empty-state').hidden=false;});
