#!/usr/bin/env node
/**
 * check-stf.js - Checks an STF directory (study.yaml, entity-<name>.{tsv,yaml})
 * for the problems that stop study-wrangler loading it. Read-only. Prints
 * ERROR:/WARNING: lines, or JSON with --json, and exits 1 if there are errors.
 *
 * Usage: node check-stf.js <stfDir> [--json]
 */
import { parseArgs } from 'node:util';
import { checkStf } from './lib/tabular/check.js';

function main() {
  const { values, positionals } = parseArgs({
    options: { json: { type: 'boolean', default: false } },
    allowPositionals: true
  });
  if (positionals.length !== 1) throw new Error('Usage: check-stf.js <stfDir> [--json]');
  const result = checkStf(positionals[0]);
  if (values.json) {
    console.log(JSON.stringify(result, null, 2));
  } else {
    for (const m of result.errors) console.log(`ERROR: ${m}`);
    for (const m of result.warnings) console.log(`WARNING: ${m}`);
  }
  process.exit(result.errors.length ? 1 : 0);
}

try {
  main();
} catch (err) {
  console.error(`Error: ${err.message}`);
  process.exit(1);
}
