#!/usr/bin/env node
/**
 * profile-tables.js - Profiles every .csv/.tsv/.txt file in a directory
 * (columns, types, top values, quirks, parent links) as compact JSON. Values
 * longer than 80 chars are cut. Read-only on the inputs.
 *
 * --file <name>  only that file's entry, and only the parent links involving
 *                it (links are still found across all files)
 * --out <path>   write the full profile to <path> and print one summary line
 *                per file instead (name, rows, columns, size of its entry)
 *
 * Usage: node profile-tables.js <inputDir> [--top N] [--file <name>] [--out <path>]
 */
import { parseArgs } from 'node:util';
import { readdirSync, statSync, writeFileSync } from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { readTable } from './lib/tabular/read-table.js';
import { profileTables } from './lib/tabular/profile.js';

const USAGE = 'Usage: profile-tables.js <inputDir> [--top N] [--file <name>] [--out <path>]';

const kb = (n) => `${(n / 1024).toFixed(1)} KB`;

function main() {
  const { values, positionals } = parseArgs({
    options: {
      top: { type: 'string', default: '20' },
      file: { type: 'string' },
      out: { type: 'string' }
    },
    allowPositionals: true
  });
  if (positionals.length !== 1) throw new Error(USAGE);
  const dir = positionals[0];
  const topN = Number(values.top);
  if (!Number.isInteger(topN) || topN < 1) throw new Error(`--top must be a positive integer, got "${values.top}"`);
  if (!statSync(dir, { throwIfNoEntry: false })?.isDirectory()) throw new Error(`Not a directory: ${dir}`);
  if (values.out && resolve(dirname(values.out)) === resolve(dir)) throw new Error(`--out must not be in the input directory ${dir}; inputs are never modified`);

  const names = readdirSync(dir).filter(n => /\.(csv|tsv|txt)$/i.test(n)).sort();
  if (names.length === 0) throw new Error(`No .csv/.tsv/.txt files in ${dir}`);
  if (values.file !== undefined && !names.includes(values.file)) throw new Error(`--file ${values.file}: no such table in ${dir} (have: ${names.join(', ')})`);
  const tables = names.map(n => readTable(join(dir, n)));
  let profile = profileTables(tables, { topN });
  if (values.file !== undefined) {
    const f = values.file;
    profile = {
      files: profile.files.filter(x => x.file === f),
      parentLinks: profile.parentLinks.filter(l => l.file === f || l.refFile === f)
    };
  }

  const text = JSON.stringify(profile);
  if (values.out === undefined) {
    console.log(text);
    return;
  }
  writeFileSync(values.out, `${text}\n`);
  console.log(`Wrote ${values.out} (${kb(Buffer.byteLength(text))}); read one file at a time with --file <name>`);
  for (const f of profile.files) {
    console.log(`${f.file}: ${f.rowCount} rows, ${f.headers.length} columns, ${kb(Buffer.byteLength(JSON.stringify(f)))}`);
  }
  console.log(`parentLinks: ${profile.parentLinks.length}`);
}

try { main(); } catch (err) { console.error(`Error: ${err.message}`); process.exit(1); }
