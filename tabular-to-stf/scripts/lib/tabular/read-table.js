/**
 * CSV/TSV reader. CSV follows RFC 4180 (quoted fields, "" escapes, embedded
 * newlines); TSV has no quoting. Values are never trimmed. Strips a UTF-8
 * BOM, treats \r\n as a line break and drops all empty lines at the end of
 * the file (an empty line before other data is still read as a row).
 * Single pass, slices rather than per-char concatenation, so linear in input.
 */

import { readFileSync } from 'node:fs';
import { extname, basename } from 'node:path';

const DELIMITER_BY_EXT = { '.csv': ',', '.tsv': '\t', '.txt': '\t' };

function fail(label, line, message) {
  return new Error(`${label}: line ${line}: ${message}`);
}

/** Split TSV text into records of cells with the physical line each starts on. */
function splitTsv(text) {
  const records = [];
  const lines = text.split('\n');
  for (let i = 0; i < lines.length; i++) {
    let l = lines[i];
    if (l.endsWith('\r')) l = l.slice(0, -1);
    records.push({ line: i + 1, cells: l.split('\t'), blank: l === '' });
  }
  return records;
}

/** RFC 4180 state machine over the whole text. */
function splitCsv(text, label) {
  const records = [];
  const n = text.length;
  let i = 0;
  let line = 1;
  while (i < n) {
    const startLine = line;
    const blank = text[i] === '\n' || (text[i] === '\r' && text[i + 1] === '\n');
    const cells = [];
    for (;;) {
      let value;
      if (text[i] === '"') {
        const openLine = line;
        let out = '';
        let segStart = ++i;
        for (;;) {
          const q = text.indexOf('"', i);
          if (q === -1) throw fail(label, openLine, 'unterminated quoted field');
          out += text.slice(segStart, q);
          if (text[q + 1] === '"') { out += '"'; i = segStart = q + 2; } else { i = q + 1; break; }
        }
        for (let k = 0; k < out.length; k++) if (out.charCodeAt(k) === 10) line++;
        value = out;
        // Anything between the closing quote and the delimiter is kept literally.
        let j = i;
        while (j < n && text[j] !== ',' && text[j] !== '\n' && text[j] !== '\r') j++;
        if (j > i) { value += text.slice(i, j); i = j; }
      } else {
        let j = i;
        while (j < n) {
          const c = text.charCodeAt(j);
          if (c === 44 || c === 10 || c === 13) break;
          j++;
        }
        value = text.slice(i, j);
        i = j;
      }
      cells.push(value);
      if (i >= n) break;
      const c = text[i];
      if (c === ',') { i++; if (i >= n) { cells.push(''); break; } continue; }
      if (c === '\r' && text[i + 1] === '\n') i++;
      i++; // the newline
      line++;
      break;
    }
    records.push({ line: startLine, cells, blank });
  }
  return records;
}

/** Parse delimited text into headers and rows. `label` names the source in errors. */
export function parseDelimited(text, delimiter, label = 'input') {
  if (text.charCodeAt(0) === 0xfeff) text = text.slice(1);
  const records = delimiter === '\t' ? splitTsv(text) : splitCsv(text, label);
  while (records.length && records[records.length - 1].blank) records.pop();
  if (records.length === 0) return { headers: [], rows: [] };
  const headers = records[0].cells;
  const rows = [];
  for (let r = 1; r < records.length; r++) {
    const { line, cells } = records[r];
    if (cells.length !== headers.length) {
      throw fail(label, line, `expected ${headers.length} cells but found ${cells.length}`);
    }
    rows.push(cells);
  }
  return { headers, rows };
}

function sniffDelimiter(text) {
  const first = text.replace(/^﻿/, '').split('\n', 1)[0];
  const tabs = first.split('\t').length - 1;
  const commas = first.split(',').length - 1;
  return tabs >= commas && tabs > 0 ? '\t' : commas > 0 ? ',' : '\t';
}

/** Read a CSV/TSV file. Delimiter comes from the extension, else line 1. */
export function readTable(path) {
  const text = readFileSync(path, 'utf8');
  const delimiter = DELIMITER_BY_EXT[extname(path).toLowerCase()] ?? sniffDelimiter(text);
  const { headers, rows } = parseDelimited(text, delimiter, basename(path));
  return { file: path, delimiter, headers, rows };
}
