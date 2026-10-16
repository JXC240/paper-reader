import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';

// The browser module is ESM, while package.json also serves older Node tools.
// Load it explicitly as ESM without changing the package's module type.
const source = await readFile(new URL('../web/search.js', import.meta.url), 'utf8');
const {buildPageText, findMatches} = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);

test('buildPageText keeps original item indices, text and half-open offsets', () => {
  const items = [
    {type: 'beginMarkedContent'},
    {str: 'Alpha', hasEOL: true},
    {str: ''},
    {str: '  beta'},
    {str: ' Gamma'},
  ];
  const page = buildPageText(items);
  assert.equal(page.text, 'Alpha\n  beta Gamma');
  assert.deepEqual(page.segments, [
    {itemIndex: 1, start: 0, end: 5},
    {itemIndex: 2, start: 6, end: 6},
    {itemIndex: 3, start: 6, end: 12},
    {itemIndex: 4, start: 12, end: 18},
  ]);
  for (const segment of page.segments) {
    assert.equal(page.text.slice(segment.start, segment.end), items[segment.itemIndex].str);
  }
});

test('literal matches ignore case but preserve original case in snippets', () => {
  const page = buildPageText([{str: 'ALPHA alpha AlPhA'}]);
  const matches = findMatches(page, 'aLpHa');
  assert.deepEqual(matches.map(({start, end}) => [start, end]), [[0, 5], [6, 11], [12, 17]]);
  assert.equal(matches[0].snippet, page.text);
});

test('whitespace folding matches across lines and maps original whitespace exactly', () => {
  const items = [{str: 'Before Alpha  ', hasEOL: true}, {str: '\tBeta\u00a0  after'}];
  const page = buildPageText(items);
  const [match] = findMatches(page, '  ALPHA\n \t beta  ');
  assert.equal(page.text.slice(match.start, match.end), 'Alpha  \n\tBeta');
  assert.deepEqual(match.parts, [{itemIndex: 0, start: 7, end: 14}, {itemIndex: 1, start: 0, end: 5}]);
  assert.equal(match.snippet, page.text);
});

test('empty runs with hasEOL retain a line break without changing item indices', () => {
  const page = buildPageText([{str: 'first'}, {str: '', hasEOL: true}, {str: 'second'}]);
  assert.equal(page.text, 'first\nsecond');
  assert.deepEqual(findMatches(page, 'first second')[0].parts, [
    {itemIndex: 0, start: 0, end: 5}, {itemIndex: 2, start: 0, end: 6},
  ]);
});

test('adjacent runs can form a single English word or Chinese phrase', () => {
  const page = buildPageText([{str: 'chrono'}, {str: 'logy '}, {str: '古'}, {str: '气候'}]);
  assert.equal(page.text, 'chronology 古气候');
  assert.deepEqual(findMatches(page, 'chronology')[0].parts, [
    {itemIndex: 0, start: 0, end: 6}, {itemIndex: 1, start: 0, end: 4},
  ]);
  assert.deepEqual(findMatches(page, '古气候')[0].parts, [
    {itemIndex: 2, start: 0, end: 1}, {itemIndex: 3, start: 0, end: 2},
  ]);
});

test('zero-width artifacts and soft hyphens are ignored only for matching', () => {
  const page = buildPageText([{str: ''}, {str: 'A co\u200boperate and re\u00adread\ufeff.'}]);
  const [cooperate] = findMatches(page, 'COOPERATE');
  const [reread] = findMatches(page, 'reread');
  assert.deepEqual(cooperate.parts, [{itemIndex: 1, start: 2, end: 12}]);
  assert.deepEqual(reread.parts, [{itemIndex: 1, start: 17, end: 24}]);
  assert.equal(page.text.slice(cooperate.start, cooperate.end), 'co\u200boperate');
  assert.equal(cooperate.snippet, page.text);
  assert.deepEqual(findMatches(buildPageText([{str: ''}, {str: '\u200b\ufeff'}]), 'word'), []);
  assert.deepEqual(findMatches(page, '\u200b\ufeff'), []);
});

test('repeated results obey default and explicit limits', () => {
  const page = buildPageText([{str: 'x '.repeat(510)}]);
  assert.equal(findMatches(page, 'x').length, 500);
  assert.equal(findMatches(page, 'x', {limit: 3}).length, 3);
  assert.equal(findMatches(page, 'x', {limit: 1.9}).length, 1);
  assert.deepEqual(findMatches(page, 'x', {limit: 0}), []);
  assert.deepEqual(findMatches(page, 'x', {limit: -1}), []);
});

test('query punctuation is literal, including regex metacharacters', () => {
  const page = buildPageText([{str: 'A [x]+ (a.b)? $5 \\ path a*b and [x]+.'}]);
  for (const query of ['[x]+', '(a.b)?', '$5', '\\', 'a*b']) {
    const matches = findMatches(page, query);
    assert.equal(matches.length, query === '[x]+' ? 2 : 1);
    for (const match of matches) assert.equal(page.text.slice(match.start, match.end), query);
  }
  assert.deepEqual(findMatches(page, '.*'), []);
});

test('Chinese text and supplementary characters retain UTF-16 offsets', () => {
  const page = buildPageText([{str: '🧪古环境论文：年代框架。古环境'}]);
  assert.deepEqual(findMatches(page, '古环境').map(match => match.parts), [
    [{itemIndex: 0, start: 2, end: 5}], [{itemIndex: 0, start: 13, end: 16}],
  ]);
  assert.deepEqual(findMatches(page, '🧪古')[0].parts, [{itemIndex: 0, start: 0, end: 3}]);
});

test('lowercase expansion does not shift the offsets of later text', () => {
  const page = buildPageText([{str: '😀İB'}]);
  assert.deepEqual(findMatches(page, 'b')[0].parts, [{itemIndex: 0, start: 3, end: 4}]);
  assert.deepEqual(findMatches(page, 'İ')[0].parts, [{itemIndex: 0, start: 2, end: 3}]);
});

test('compatibility ligatures and fullwidth letters map to original characters', () => {
  const page = buildPageText([{str: 'The oﬃce uses ＡＩ. ﬃ'}]);
  const [office] = findMatches(page, 'OFFICE');
  assert.deepEqual(office.parts, [{itemIndex: 0, start: 4, end: 8}]);
  assert.equal(page.text.slice(office.start, office.end), 'oﬃce');
  assert.equal(office.snippet, page.text);
  assert.equal(page.text.slice(...['start', 'end'].map(key => findMatches(page, 'ai')[0][key])), 'ＡＩ');
  assert.equal(findMatches(buildPageText([{str: 'ﬃ'}]), 'f').length, 1);
  assert.deepEqual(findMatches(buildPageText([{str: 'ﬃ'}]), 'ffi')[0].parts, [{itemIndex: 0, start: 0, end: 1}]);
});

test('no-result and empty inputs return empty arrays', () => {
  const page = buildPageText([{str: 'A sentence.'}]);
  for (const query of ['', ' \n\t ', 'absent', null]) assert.deepEqual(findMatches(page, query), []);
  assert.deepEqual(buildPageText([]), {text: '', segments: []});
  assert.deepEqual(buildPageText(null), {text: '', segments: []});
  assert.deepEqual(findMatches(buildPageText([]), 'sentence'), []);
  assert.deepEqual(findMatches(null, 'sentence'), []);
});

test('parts select exact substrings in every original item without mutation', () => {
  const items = Object.freeze([
    Object.freeze({str: 'prefix 🧪mIx', hasEOL: true}),
    Object.freeze({type: 'beginMarkedContent'}),
    Object.freeze({str: ''}),
    Object.freeze({str: '\tCase\u200b TEXT suffix'}),
  ]);
  const page = buildPageText(items);
  const before = JSON.stringify(page);
  const [match] = findMatches(page, 'mix case text');
  assert.deepEqual(match.parts, [{itemIndex: 0, start: 9, end: 12}, {itemIndex: 3, start: 0, end: 11}]);
  assert.deepEqual(match.parts.map(part => items[part.itemIndex].str.slice(part.start, part.end)), ['mIx', '\tCase\u200b TEXT']);
  assert.equal(JSON.stringify(page), before);
});

test('long snippets contain original text and do not split supplementary characters', () => {
  const page = buildPageText([{str: '🧪'.repeat(60) + ' Needle\n' + '🧪'.repeat(60)}]);
  const [match] = findMatches(page, 'needle');
  assert.ok(match.snippet.includes(' Needle\n'));
  assert.ok(match.snippet.startsWith('…'));
  assert.ok(match.snippet.endsWith('…'));
  assert.ok(!/(?<![\ud800-\udbff])[\udc00-\udfff]|[\ud800-\udbff](?![\udc00-\udfff])/u.test(match.snippet));
});
