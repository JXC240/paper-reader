import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';

const source = await readFile(new URL('../web/clipboard.js', import.meta.url), 'utf8');
const {copyText} = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);

function fallbackControls() {
  const field = {
    value:'', focused:false, selected:'',
    focus() { this.focused = true; },
    select() { this.selected = this.value; },
    set innerHTML(value) { throw new Error('Copy fallback must not render HTML'); },
  };
  const dialog = {open:false, showModal() { this.open = true; }};
  return {dialog, field};
}

test('successful clipboard write keeps the fallback closed', async () => {
  const controls = fallbackControls(), writes = [];
  const copied = await copyText('A reading question.\n第 1 页', {
    ...controls, clipboard:{async writeText(text) { writes.push(text); }},
  });
  assert.equal(copied, true);
  assert.deepEqual(writes, ['A reading question.\n第 1 页']);
  assert.equal(controls.dialog.open, false);
  assert.equal(controls.field.value, '');
  assert.equal(controls.field.focused, false);
});

test('denied permission offers the complete paper link for manual copying', async () => {
  const controls = fallbackControls(), text = 'http://127.0.0.1:8877/?doc=abc123';
  const copied = await copyText(text, {
    ...controls, clipboard:{async writeText() { throw new Error('NotAllowedError'); }},
  });
  assert.equal(copied, false);
  assert.equal(controls.dialog.open, true);
  assert.equal(controls.field.focused, true);
  assert.equal(controls.field.selected, text);
});

test('missing Clipboard API still offers complete multiline reading context', async () => {
  const controls = fallbackControls(), text = '论文：Demo.pdf\nPDF 第 2 页\n原文：Keep the context.\n笔记：待核对。';
  assert.equal(await copyText(text, {...controls, clipboard:undefined}), false);
  assert.equal(controls.dialog.open, true);
  assert.equal(controls.field.focused, true);
  assert.equal(controls.field.value, text);
  assert.equal(controls.field.selected, text);
});

test('HTML characters stay literal and a second fallback replaces old content', async () => {
  const controls = fallbackControls();
  await copyText('previous text', controls);
  const text = '</textarea><img src=x onerror="alert(1)">\nA & B < C; "quoted"';
  assert.equal(await copyText(text, controls), false);
  assert.equal(controls.dialog.open, true);
  assert.equal(controls.field.value, text);
  assert.equal(controls.field.selected, text);
});
