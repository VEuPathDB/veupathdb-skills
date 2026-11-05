#!/usr/bin/env node
/**
 * validate-stf-in-container.js - Validates an STF directory with study-wrangler
 * in its pinned container (baseline and eda profiles, geo variables inferred).
 * Needs docker or podman and the image already present; never pulls it.
 * Prints the validator output, then "Result: pass|fail|error|load-error".
 * Exits 0 on pass, 1 on fail, 2 on error or load-error, 3 when there is no container engine.
 *
 * Usage: node validate-stf-in-container.js <stfDir> [--engine docker|podman]
 *        node validate-stf-in-container.js --detect
 */
import { parseArgs } from 'node:util';
import { detectEngine, validateStudyInContainer } from './lib/tools/study-wrangler-container.js';

const EXIT = { pass: 0, fail: 1, error: 2, 'load-error': 2 };

function main() {
  const { values, positionals } = parseArgs({
    options: { engine: { type: 'string' }, detect: { type: 'boolean', default: false } },
    allowPositionals: true
  });
  if (values.engine && !['docker', 'podman'].includes(values.engine)) throw new Error('--engine must be docker or podman');
  const engine = detectEngine({ preferred: values.engine });
  if (values.detect) {
    console.log(engine ?? 'none');
    return;
  }
  if (positionals.length !== 1) throw new Error('Usage: validate-stf-in-container.js <stfDir> [--engine docker|podman] | --detect');
  if (!engine) {
    console.error('No container engine (docker or podman) found');
    process.exit(3);
  }
  const { status, output } = validateStudyInContainer(positionals[0], { engine });
  console.log(output);
  console.log(`Result: ${status}`);
  process.exit(EXIT[status]);
}

try {
  main();
} catch (err) {
  console.error(`Error: ${err.message}`);
  process.exit(1);
}
