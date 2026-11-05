/**
 * Input profiler. Turns parsed tables into a capped, compact JSON profile the
 * curator reads instead of whole files. Values shown (top, sampleRows,
 * nearDuplicates) are cut to MAX_VALUE_LENGTH chars. One pass per column over the rows,
 * counting values in a Map; everything else is derived from those counts, so
 * rows are never copied and cost stays linear in cells.
 */

import { basename } from 'node:path';
import { inferType } from '../stf-common.js';

export const PLACEHOLDERS = ['NA', 'N/A', 'n/a', 'na', '-', '--', '.', 'null', 'NULL', 'none', 'None', 'unknown', 'Unknown', 'not done'];
export const UNAMBIGUOUS_PLACEHOLDERS = ['NA', 'N/A', 'n/a', 'na', '-', '--', '.', 'null', 'NULL'];

export const MAX_VALUE_LENGTH = 80;
const NEAR_DUPLICATE_MAX_DISTINCT = 200;

/** Cuts a long cell value to `max` chars plus a note of how many were dropped. */
export function truncateValue(v, max = MAX_VALUE_LENGTH) {
  return typeof v === 'string' && v.length > max ? `${v.slice(0, max)}…[+${v.length - max} chars]` : v;
}
const LEVENSHTEIN_MIN_LENGTH = 5;
const LEVENSHTEIN_MAX_DISTANCE = 2;

function levenshtein(a, b, max) {
  if (Math.abs(a.length - b.length) > max) return max + 1;
  let prev = Array.from({ length: b.length + 1 }, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    const cur = [i];
    for (let j = 1; j <= b.length; j++) {
      cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
    }
    prev = cur;
  }
  return prev[b.length];
}

/**
 * Pairs of values that differ only by case/whitespace, then pairs within
 * Levenshtein distance; each group sorted. Returns the total found and the
 * first `cap` pairs.
 */
function findNearDuplicates(values, cap) {
  const equal = [];
  const close = [];
  for (let i = 0; i < values.length; i++) {
    for (let j = i + 1; j < values.length; j++) {
      const a = values[i];
      const b = values[j];
      const pair = a < b ? [a, b] : [b, a];
      if (a.toLowerCase().trim() === b.toLowerCase().trim()) equal.push(pair);
      else if (a.length >= LEVENSHTEIN_MIN_LENGTH && b.length >= LEVENSHTEIN_MIN_LENGTH
        && levenshtein(a, b, LEVENSHTEIN_MAX_DISTANCE) <= LEVENSHTEIN_MAX_DISTANCE) close.push(pair);
    }
  }
  const byPair = (x, y) => (x[0] < y[0] ? -1 : x[0] > y[0] ? 1 : x[1] < y[1] ? -1 : x[1] > y[1] ? 1 : 0);
  const all = [...equal.sort(byPair), ...close.sort(byPair)];
  return { count: all.length, pairs: all.slice(0, cap) };
}

/** Profile column `c` of `rows`; returns the profile and the value counts. */
function profileColumn(header, c, rows, topN) {
  const counts = new Map();
  let whitespaceCells = 0;
  for (let r = 0; r < rows.length; r++) {
    const v = rows[r][c] ?? '';
    counts.set(v, (counts.get(v) ?? 0) + 1);
  }
  const placeholderCells = {};
  let leadingZeros = false;
  for (const [v, n] of counts) {
    if (v !== v.trim()) whitespaceCells += n;
    if (PLACEHOLDERS.includes(v)) placeholderCells[v] = n;
    if (/^0\d/.test(v)) leadingZeros = true;
  }
  const distinct = [...counts.keys()];
  // inferType only asks "do all/any values match", so the distinct values decide it.
  const inferred = inferType(distinct);
  const top = [...counts]
    .sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0))
    .slice(0, topN)
    .map(([value, count]) => ({ value: truncateValue(value), count }));
  const column = { header, distinctCount: counts.size, top, inferred };

  const nonEmpty = distinct.filter(v => v !== '');
  if (nonEmpty.length > 0) {
    if (inferred.data_type === 'number' || inferred.data_type === 'integer') {
      let min = Infinity;
      let max = -Infinity;
      for (const v of nonEmpty) {
        const x = Number(v);
        if (x < min) min = x;
        if (x > max) max = x;
      }
      column.min = min;
      column.max = max;
    } else if (inferred.data_type === 'date') {
      const sorted = nonEmpty.slice().sort();
      column.min = sorted[0];
      column.max = sorted[sorted.length - 1];
    }
  }

  column.isCandidateId = rows.length > 0 && counts.size === rows.length && !counts.has('');
  column.leadingZeros = leadingZeros;
  column.whitespaceCells = whitespaceCells;
  column.placeholderCells = placeholderCells;
  // Unique IDs differ by construction (sample001, sample002), so pairs there are noise.
  const near = inferred.data_shape === 'categorical' && !column.isCandidateId && counts.size <= NEAR_DUPLICATE_MAX_DISTINCT
    ? findNearDuplicates(nonEmpty, topN)
    : { count: 0, pairs: [] };
  column.nearDuplicates = near.pairs.map((pair) => pair.map((v) => truncateValue(v)));
  column.nearDuplicateCount = near.count;
  return { column, counts };
}

/** Column C of F links to candidate ID K of another file G if every value of C is in K. */
function findParentLinks(entries) {
  // Keep a column's values only if it can be a link target (candidate ID) or
  // could be wholly contained in another file's candidate ID; free the rest.
  for (const f of entries) {
    const otherMax = Math.max(0, ...entries.filter(g => g !== f)
      .flatMap(g => g.columns.filter(c => c.isCandidateId).map(c => c.distinctCount)));
    f.columns.forEach((col, ci) => {
      // Link detection ignores blanks, so compare on the non-empty distinct count.
      const nonEmpty = f.counts[ci].size - (f.counts[ci].has('') ? 1 : 0);
      if (!col.isCandidateId && nonEmpty > otherMax) f.counts[ci] = null;
    });
  }
  const links = [];
  for (const f of entries) {
    const candidateCount = f.columns.filter(c => c.isCandidateId).length;
    f.columns.forEach((col, ci) => {
      if (col.isCandidateId && candidateCount === 1) return;
      if (!f.counts[ci]) return;
      const values = [...f.counts[ci].keys()].filter(v => v !== '');
      if (values.length === 0) return;
      for (const g of entries) {
        if (g === f) continue;
        g.columns.forEach((gcol, gi) => {
          if (!gcol.isCandidateId) return;
          const keys = g.counts[gi];
          if (values.every(v => keys.has(v))) {
            links.push({ file: f.file, column: col.header, refFile: g.file, refColumn: gcol.header });
          }
        });
      }
    });
  }
  return links;
}

export function profileTables(tables, { topN = 20, sampleRows = 5 } = {}) {
  const entries = tables.map((t) => {
    const profiled = t.headers.map((h, c) => profileColumn(h, c, t.rows, topN));
    return {
      file: basename(t.file),
      delimiter: t.delimiter,
      rowCount: t.rows.length,
      headers: t.headers,
      sampleRows: t.rows.slice(0, sampleRows).map((r) => r.map((v) => truncateValue(v))),
      columns: profiled.map(p => p.column),
      counts: profiled.map(p => p.counts)
    };
  });
  const parentLinks = findParentLinks(entries);
  return {
    files: entries.map(({ counts, ...file }) => file),
    parentLinks
  };
}
