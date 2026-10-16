// PDF.js item strings and DOM Range offsets both use UTF-16 code units.
// Keep the original strings here; normalization is only for finding matches.
export function buildPageText(items) {
  let text = '';
  const segments = [];
  for (const [itemIndex, item] of (Array.isArray(items) ? items : []).entries()) {
    if (typeof item?.str !== 'string') continue;
    const str = item.str;
    // A word can span several runs (especially Chinese text). PDF.js supplies
    // actual spaces in str and explicit line breaks in hasEOL; add no others.
    const start = text.length;
    text += str;
    segments.push({itemIndex, start, end: text.length});
    if (item.hasEOL) text += '\n';
  }
  return {text, segments};
}

function normalizeWithOffsets(text) {
  let normalized = '';
  const starts = [], ends = [];
  for (let offset = 0; offset < text.length;) {
    const original = String.fromCodePoint(text.codePointAt(offset));
    const end = offset + original.length;
    // These PDF artifacts have no visible character to highlight. Preserve them
    // in the original text but allow a word to match across them.
    if (/[\u00ad\u200b\ufeff]/u.test(original)) {
      offset = end;
      continue;
    }
    // Per-character compatibility normalization handles common PDF ligatures
    // (for example, ﬃ → ffi) while retaining their original source span.
    const folded = original.normalize('NFKC').toLowerCase();
    for (const character of folded) {
      if (/\s/u.test(character)) {
        if (normalized.endsWith(' ')) {
          ends[ends.length - 1] = end;
        } else {
          normalized += ' ';
          starts.push(offset);
          ends.push(end);
        }
      } else {
        normalized += character;
        // A supplementary character occupies two UTF-16 offsets in indexOf.
        for (let unit = 0; unit < character.length; unit++) {
          starts.push(offset);
          ends.push(end);
        }
      }
    }
    offset = end;
  }
  return {text: normalized, starts, ends};
}

function nearbyOriginal(text, start, end) {
  let from = Math.max(0, start - 45), to = Math.min(text.length, end + 65);
  // Do not cut an emoji or other supplementary character in half.
  if (from > 0 && /[\udc00-\udfff]/u.test(text[from])) from--;
  if (to < text.length && /[\udc00-\udfff]/u.test(text[to])) to++;
  return (from > 0 ? '…' : '') + text.slice(from, to) + (to < text.length ? '…' : '');
}

/**
 * Find non-overlapping, literal matches. start/end refer to pageText.text;
 * parts refer to offsets inside the original item.str, ready for DOM Range.
 * snippet preserves original case, whitespace and ligatures, not search text.
 */
export function findMatches(pageText, query, {limit = 500} = {}) {
  if (typeof pageText?.text !== 'string' || !Array.isArray(pageText.segments) || typeof query !== 'string') return [];
  const maximum = Number.isFinite(limit) ? Math.max(0, Math.floor(limit)) : 500;
  if (!maximum) return [];
  const needle = normalizeWithOffsets(query).text.trim();
  if (!needle) return [];
  const haystack = normalizeWithOffsets(pageText.text);
  const matches = [];
  let offset = 0, previousStart = -1, previousEnd = -1;
  while (matches.length < maximum) {
    const found = haystack.text.indexOf(needle, offset);
    if (found === -1) break;
    offset = found + needle.length;
    const start = haystack.starts[found], end = haystack.ends[offset - 1];
    // A query such as "f" can hit two letters within a single ﬃ ligature.
    // One original character should produce one search box and result entry.
    if (start === previousStart && end === previousEnd) continue;
    const parts = [];
    for (const segment of pageText.segments) {
      if (segment.start >= end) break;
      const partStart = Math.max(start, segment.start), partEnd = Math.min(end, segment.end);
      if (partStart < partEnd) parts.push({itemIndex: segment.itemIndex, start: partStart - segment.start, end: partEnd - segment.start});
    }
    if (!parts.length) continue;
    matches.push({start, end, parts, snippet: nearbyOriginal(pageText.text, start, end)});
    previousStart = start;
    previousEnd = end;
  }
  return matches;
}
