import { existsSync, statSync } from 'node:fs';
import { resolve, join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { defaultExec, failureOutput } from './exec.js';

export const STUDY_WRANGLER_VERSION = '1.0.54';
export const STUDY_WRANGLER_IMAGE = `veupathdb/study-wrangler:${STUDY_WRANGLER_VERSION}`;

const SCRIPT = join(dirname(fileURLToPath(import.meta.url)), 'study-wrangler-validate-study.R');

/** 'docker' | 'podman' | null: the first engine that answers `version`; only `preferred` if given. */
export function detectEngine({ exec = defaultExec, preferred } = {}) {
  for (const engine of preferred ? [preferred] : ['docker', 'podman']) {
    try { exec(engine, ['version']); return engine; }
    catch { /* not installed, or its daemon is down */ }
  }
  return null;
}

const MAX_BUFFER = 64 * 1024 * 1024; // verbose per-entity output on a big study

/**
 * Arguments for `<engine> ...`. Read-only mounts, so nothing is written as root; never pulls the image.
 * Docker's -v would create a missing source as a root-owned directory, so it gets --mount, which errors.
 * Podman keeps -v with ,Z (SELinux relabel): its --mount relabel option could not be confirmed.
 */
export function containerArgs(engine, stfDir, scriptPath) {
  const mounts = [[resolve(stfDir), '/stf'], [resolve(scriptPath), '/sw/validate-study.R']].flatMap(([src, dst]) =>
    engine === 'podman' ? ['-v', `${src}:${dst}:ro,Z`] : ['--mount', `type=bind,src=${src},dst=${dst},readonly`]);
  return ['run', '--rm', '--pull=never', ...mounts, STUDY_WRANGLER_IMAGE, 'Rscript', '/sw/validate-study.R', '/stf'];
}

/**
 * Validates an STF directory in the pinned container: { status, output }. status is 'pass', 'fail',
 * 'error' (it loaded, but geo inference or validate() raised an R error: STF_VALIDATION_ERROR) or
 * 'load-error' (STF_LOAD_ERROR, or no marker at all: the container or R stopped before loading).
 */
export function validateStudyInContainer(stfDir, { engine = detectEngine(), exec = defaultExec } = {}) {
  if (!engine) throw new Error('No container engine (docker or podman) found');
  if (!existsSync(stfDir) || !statSync(stfDir).isDirectory()) throw new Error(`STF directory not found: ${stfDir}`);
  if (!existsSync(SCRIPT)) throw new Error(`Validator script not found: ${SCRIPT}`);
  let output;
  try { output = exec(engine, containerArgs(engine, stfDir, SCRIPT), { maxBuffer: MAX_BUFFER }).trim(); }
  catch (e) { output = failureOutput(e); }
  // the engine's own failures (no image, no daemon) carry no marker, so they are load-errors too
  const status = /^STF_VALIDATION: PASS\s*$/m.test(output) ? 'pass'
    : /^STF_VALIDATION: FAIL\s*$/m.test(output) ? 'fail'
      : /^STF_VALIDATION_ERROR:/m.test(output) ? 'error' : 'load-error';
  return { status, output };
}
