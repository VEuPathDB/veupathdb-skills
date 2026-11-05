/**
 * Minimal YAML reader for the subset STF files use: block mappings and
 * sequences, plain/single/double-quoted scalars, flow sequences of scalars,
 * `{}`, block scalars (| > |- >-) and comments. Anything else (anchors,
 * aliases, tags, extra documents, flow mappings with content) throws
 * YamlLiteError. Pure.
 */

export class YamlLiteError extends Error {
  constructor(message, line) {
    super(`line ${line}: ${message}`);
    this.name = 'YamlLiteError';
    this.line = line;
  }
}

// Plain scalars: numbers, booleans and null resolve; yes/no stay strings
function plainValue(s) {
  if (s === '' || /^(null|~)$/i.test(s)) return null;
  if (/^(true|false)$/i.test(s)) return s.toLowerCase() === 'true';
  if (/^-?\d+$/.test(s) || /^-?(\d+\.\d+|\.\d+)$/.test(s)) return Number(s);
  return s;
}

const DQ_ESCAPES = { '"': '"', '\\': '\\', n: '\n', r: '\r', t: '\t' };

// Reads a quoted scalar at s[start]; returns { value, end } (end is past the closing quote)
function readQuoted(s, start, lineNo) {
  const q = s[start];
  let out = '';
  let i = start + 1;
  while (i < s.length) {
    const c = s[i];
    if (q === "'") {
      if (c === "'") {
        if (s[i + 1] === "'") { out += "'"; i += 2; continue; }
        return { value: out, end: i + 1 };
      }
      out += c; i++;
    } else {
      if (c === '"') return { value: out, end: i + 1 };
      if (c === '\\') {
        const e = DQ_ESCAPES[s[i + 1]];
        if (e === undefined) throw new YamlLiteError(`unsupported escape \\${s[i + 1] ?? ''}`, lineNo);
        out += e; i += 2; continue;
      }
      out += c; i++;
    }
  }
  throw new YamlLiteError('unterminated quoted string', lineNo);
}

function requireOnlyComment(rest, lineNo) {
  const t = rest.trim();
  if (t !== '' && !t.startsWith('#')) throw new YamlLiteError(`unexpected text after value: ${t}`, lineNo);
}

function rejectIndicator(s, lineNo) {
  if (/^[&*!]/.test(s)) throw new YamlLiteError(`unsupported YAML construct: ${s[0]}`, lineNo);
}

function parseFlow(s, lineNo) {
  // s starts with '[' or '{'
  if (s[0] === '{') {
    const m = /^\{\s*\}(.*)$/.exec(s);
    if (!m) throw new YamlLiteError('flow mappings with content are not supported', lineNo);
    requireOnlyComment(m[1], lineNo);
    return {};
  }
  const items = [];
  let i = 1;
  for (;;) {
    while (s[i] === ' ') i++;
    if (i >= s.length) throw new YamlLiteError('unterminated flow sequence (multi-line flow is not supported)', lineNo);
    if (s[i] === ']') { i++; break; }
    if (s[i] === '[' || s[i] === '{') throw new YamlLiteError('nested flow collections are not supported', lineNo);
    rejectIndicator(s.slice(i), lineNo);
    if (s[i] === "'" || s[i] === '"') {
      const { value, end } = readQuoted(s, i, lineNo);
      items.push(value);
      i = end;
    } else {
      let j = i;
      while (j < s.length && s[j] !== ',' && s[j] !== ']') j++;
      if (j >= s.length) throw new YamlLiteError('unterminated flow sequence (multi-line flow is not supported)', lineNo);
      items.push(plainValue(s.slice(i, j).trim()));
      i = j;
    }
    while (s[i] === ' ') i++;
    if (s[i] === ',') { i++; continue; }
    if (s[i] === ']') { i++; break; }
    throw new YamlLiteError('expected , or ] in flow sequence', lineNo);
  }
  requireOnlyComment(s.slice(i), lineNo);
  return items;
}

// A scalar or flow value on one line (comments allowed after it)
function parseInline(s, lineNo) {
  rejectIndicator(s, lineNo);
  if (s[0] === "'" || s[0] === '"') {
    const { value, end } = readQuoted(s, 0, lineNo);
    requireOnlyComment(s.slice(end), lineNo);
    return value;
  }
  if (s[0] === '[' || s[0] === '{') return parseFlow(s, lineNo);
  const m = /(^|\s)#/.exec(s);
  return plainValue((m ? s.slice(0, m.index) : s).trim());
}

// Splits 'key: rest' or 'key:'; returns null if the text is not a mapping entry
function splitKey(text, lineNo) {
  if (text[0] === "'" || text[0] === '"') {
    const { value, end } = readQuoted(text, 0, lineNo);
    const m = /^\s*:(\s+(.*)|)$/.exec(text.slice(end));
    return m ? { key: value, rest: (m[2] ?? '').trim() } : null;
  }
  if (/^[\[{]/.test(text)) return null;
  const m = /^(.*?):(?:\s+(.*)|)$/.exec(text);
  if (!m || m[1] === '' || /\s#/.test(m[1])) return null;
  rejectIndicator(m[1], lineNo);
  return { key: m[1].trim(), rest: (m[2] ?? '').trim() };
}

export function parseYaml(text) {
  const lines = String(text).replace(/^﻿/, '').split(/\r?\n/).map((raw, i) => {
    const content = raw.trimStart();
    const indent = raw.length - content.length;
    if (raw.slice(0, indent).includes('\t')) {
      throw new YamlLiteError('tabs are not allowed in indentation', i + 1);
    }
    return { raw, indent, text: content.trimEnd(), no: i + 1 };
  });
  let pos = 0;
  let sawDocStart = false;

  // Next line that is neither blank nor comment-only (not consumed)
  function peek() {
    while (pos < lines.length && (lines[pos].text === '' || lines[pos].text.startsWith('#'))) pos++;
    if (pos >= lines.length) return null;
    const l = lines[pos];
    if (l.indent === 0 && /^(---|\.\.\.)(\s|$)/.test(l.text)) {
      if (l.text.startsWith('---') && !sawDocStart && lines.slice(0, pos).every(x => x.text === '' || x.text.startsWith('#'))) {
        sawDocStart = true;
        if (l.text.slice(3).trim() !== '') throw new YamlLiteError('content on a document-start line is not supported', l.no);
        pos++;
        return peek();
      }
      throw new YamlLiteError('multiple documents are not supported', l.no);
    }
    return l;
  }

  function blockScalar(style, chomp, parentIndent, lineNo) {
    const body = [];
    while (pos < lines.length) {
      const l = lines[pos];
      if (l.text !== '' && l.indent <= parentIndent) break;
      body.push(l);
      pos++;
    }
    const firstReal = body.find(l => l.text !== '');
    if (!firstReal) return '';
    const bi = firstReal.indent;
    let rows = body.map(l => (l.text === '' ? '' : l.raw.slice(bi).trimEnd()));
    let trailing = 0;
    while (rows.length && rows[rows.length - 1] === '') { rows.pop(); trailing++; }
    let out;
    if (style === '|') {
      out = rows.join('\n');
    } else {
      out = '';
      rows.forEach((r, i) => {
        if (i === 0) { out = r; return; }
        const prev = rows[i - 1];
        if (r === '') out += '\n';
        else if (prev === '') out += r.startsWith(' ') ? '\n' + r : r;
        else out += (r.startsWith(' ') || prev.startsWith(' ') ? '\n' : ' ') + r;
      });
    }
    if (chomp === '-') return out;
    if (chomp === '+') return out + '\n'.repeat(trailing + 1);
    return out + '\n';
  }

  // Value following 'key:' or '- ' on the same line; parentIndent bounds block scalars
  function inlineValue(rest, parentIndent, line) {
    const bs = /^([|>])([+-]?)\s*(#.*)?$/.exec(rest);
    if (bs) { pos++; return blockScalar(bs[1], bs[2], parentIndent, line.no); }
    pos++;
    return parseInline(rest, line.no);
  }

  function parseNode(indent) {
    const l = lines[pos];
    if (/^-(\s|$)/.test(l.text)) return parseSeq(indent);
    if (splitKey(l.text, l.no)) return parseMap(indent);
    pos++;
    return parseInline(l.text, l.no);
  }

  // Nested value on the lines after 'key:' / '-'; seqOk allows a sequence at the key's own indent
  function nested(indent, seqOk) {
    const n = peek();
    if (n && n.indent > indent) return parseNode(n.indent);
    if (seqOk && n && n.indent === indent && /^-(\s|$)/.test(n.text)) return parseSeq(indent);
    return null;
  }

  function parseSeq(indent) {
    const out = [];
    for (;;) {
      const l = peek();
      if (!l || l.indent !== indent || !/^-(\s|$)/.test(l.text)) break;
      const afterDash = l.text.slice(1);
      const rest = afterDash.trim();
      if (rest === '' || rest.startsWith('#')) {
        pos++;
        out.push(nested(indent, false));
        continue;
      }
      const offset = 1 + (afterDash.length - afterDash.trimStart().length);
      if (/^-(\s|$)/.test(rest) || splitKey(rest, l.no)) {
        // '- key: v' / '- - x': reread the remainder as a node indented past the dash
        l.indent += offset;
        l.text = rest;
        out.push(parseNode(l.indent));
      } else {
        out.push(inlineValue(rest, indent, l));
      }
    }
    return out;
  }

  function parseMap(indent) {
    const out = {};
    for (;;) {
      const l = peek();
      if (!l) break;
      if (l.indent < indent) break;
      if (l.indent > indent) throw new YamlLiteError('unexpected indentation', l.no);
      const kv = splitKey(l.text, l.no);
      if (!kv) throw new YamlLiteError(`expected 'key: value', got: ${l.text}`, l.no);
      if (kv.rest === '' || kv.rest.startsWith('#')) {
        pos++;
        out[kv.key] = nested(indent, true);
      } else {
        out[kv.key] = inlineValue(kv.rest, indent, l);
      }
    }
    return out;
  }

  const first = peek();
  if (!first) return null;
  const result = parseNode(first.indent);
  const extra = peek();
  if (extra) throw new YamlLiteError('unexpected content', extra.no);
  return result;
}
