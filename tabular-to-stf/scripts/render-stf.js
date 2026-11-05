#!/usr/bin/env node
/**
 * render-stf.js - Renders a curation spec and its input tables to an STF
 * directory: study.yaml, entity-<name>.{tsv,yaml}, curation-notes.md, a copy
 * of the spec (curation-spec.json) and, by default, raw-data/ holding
 * unmodified copies of the inputs. The saved spec then reads from raw-data/,
 * so `render-stf.js <outDir>/curation-spec.json <outDir>` re-renders from the
 * folder alone. Input files are never modified.
 *
 * Usage: node render-stf.js <spec.json> <outDir> [--no-raw-data]
 */
import { parseArgs } from 'node:util';
import { readFileSync, writeFileSync, mkdirSync, copyFileSync, existsSync, readdirSync } from 'node:fs';
import { join, dirname, resolve, isAbsolute } from 'node:path';
import { readTable } from './lib/tabular/read-table.js';
import { renderStf, RenderError } from './lib/tabular/render.js';
import { validateSpec } from './lib/tabular/spec.js';
import { SAVED_SPEC } from './lib/tabular/notes.js';

const RAW = 'raw-data';

function main() {
  const { values, positionals } = parseArgs({
    options: { 'no-raw-data': { type: 'boolean', default: false } },
    allowPositionals: true
  });
  if (positionals.length !== 2) throw new Error('Usage: render-stf.js <spec.json> <outDir> [--no-raw-data]');
  const [specPath, outArg] = positionals;
  const outDir = resolve(outArg);
  const copyRaw = !values['no-raw-data'];

  const spec = JSON.parse(readFileSync(specPath, 'utf8'));
  const specErrors = validateSpec(spec);
  if (specErrors.length) throw new RenderError(specErrors);
  const inputDir = isAbsolute(spec.inputDir) ? spec.inputDir : resolve(dirname(specPath), spec.inputDir);

  if (existsSync(outDir) && readdirSync(outDir).length > 0 && !existsSync(join(outDir, SAVED_SPEC))) {
    throw new Error(`${outDir} is not empty and has no ${SAVED_SPEC}; choose an empty or new directory`);
  }

  const tables = new Map(spec.entities.map((e) => {
    const { headers, rows } = readTable(join(inputDir, e.file));
    return [e.name, { headers, rows }];
  }));
  const { files } = renderStf(spec, tables, { sourceDir: copyRaw ? RAW : inputDir });

  // Plan the raw-data copies before writing anything: a same-named file with other bytes is an error
  const rawDir = join(outDir, RAW);
  const copies = [];
  if (copyRaw && resolve(inputDir) !== rawDir) {
    const names = [...new Set([...spec.entities.map((e) => e.file), ...(spec.extraFiles || [])])];
    for (const name of names) {
      const from = join(inputDir, name);
      const to = join(rawDir, name);
      const bytes = readFileSync(from);
      if (existsSync(to)) {
        if (!readFileSync(to).equals(bytes)) throw new Error(`${RAW}/${name} differs from ${from}; inputs are immutable, so render into a new directory`);
      } else {
        copies.push([from, to]);
      }
    }
  } else if (copyRaw) {
    for (const name of spec.extraFiles || []) {
      if (!existsSync(join(rawDir, name))) throw new Error(`extra file not found: ${join(rawDir, name)}`);
    }
  }

  mkdirSync(outDir, { recursive: true });
  for (const [from, to] of copies) {
    mkdirSync(dirname(to), { recursive: true });
    copyFileSync(from, to);
  }
  const saved = { ...spec, inputDir: copyRaw ? RAW : inputDir };
  const written = { ...files, [SAVED_SPEC]: `${JSON.stringify(saved, null, 2)}\n` };
  for (const [name, text] of Object.entries(written)) writeFileSync(join(outDir, name), text);

  for (const name of Object.keys(written)) console.log(join(outDir, name));
  for (const [, to] of copies) console.log(to);
}

try {
  main();
} catch (err) {
  if (err instanceof RenderError) {
    console.error('Error: the spec does not render:');
    for (const m of err.messages) console.error(`- ${m}`);
  } else {
    console.error(`Error: ${err.message}`);
  }
  process.exit(1);
}
