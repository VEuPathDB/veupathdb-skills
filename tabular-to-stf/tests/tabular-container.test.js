import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, cpSync, readFileSync, writeFileSync, rmSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { spawnSync } from 'node:child_process';
import {
  STUDY_WRANGLER_VERSION, STUDY_WRANGLER_IMAGE, detectEngine, containerArgs, validateStudyInContainer
} from '../scripts/lib/tools/study-wrangler-container.js';
import { checkStf } from '../scripts/lib/tabular/check.js';

const fixtures = new URL('./fixtures/tabular/', import.meta.url).pathname;
const cli = new URL('../scripts/validate-stf-in-container.js', import.meta.url).pathname;
const script = new URL('../scripts/lib/tools/study-wrangler-validate-study.R', import.meta.url).pathname;

const temps = [];
after(() => { for (const d of temps) rmSync(d, { recursive: true, force: true }); });

const failing = (props) => Object.assign(new Error('Command failed'), props);

test('the image is pinned to one version constant', () => {
  assert.equal(STUDY_WRANGLER_VERSION, '1.0.56');
  assert.equal(STUDY_WRANGLER_IMAGE, 'veupathdb/study-wrangler:1.0.56');
});

test('containerArgs mounts read-only, never pulls, and docker refuses a missing source', () => {
  assert.deepEqual(containerArgs('docker', 'stf', '/x/v.R'), [
    'run', '--rm', '--pull=never',
    '--mount', `type=bind,src=${resolve('stf')},dst=/stf,readonly`,
    '--mount', 'type=bind,src=/x/v.R,dst=/sw/validate-study.R,readonly',
    STUDY_WRANGLER_IMAGE, 'Rscript', '/sw/validate-study.R', '/stf'
  ]);
  assert.deepEqual(containerArgs('podman', '/d/stf', '/x/v.R'), [
    'run', '--rm', '--pull=never',
    '-v', '/d/stf:/stf:ro,Z',
    '-v', '/x/v.R:/sw/validate-study.R:ro,Z',
    STUDY_WRANGLER_IMAGE, 'Rscript', '/sw/validate-study.R', '/stf'
  ]);
});

test('a missing directory or a file is refused before the engine runs', () => {
  const exec = () => assert.fail('exec must not run');
  assert.throws(() => validateStudyInContainer('/nonexistent-xyz-stf', { engine: 'docker', exec }), /STF directory not found: \/nonexistent-xyz-stf/);
  assert.throws(() => validateStudyInContainer(script, { engine: 'docker', exec }), /STF directory not found/);
});

test('exec gets a large maxBuffer', () => {
  let opts;
  validateStudyInContainer(fixtures, { engine: 'docker', exec: (c, a, o) => { opts = o; return 'STF_VALIDATION: PASS'; } });
  assert.equal(opts.maxBuffer, 64 * 1024 * 1024);
});

test('detectEngine tries docker first, then podman, then gives up', () => {
  const tried = [];
  const only = (ok) => (cmd, args) => { tried.push([cmd, ...args]); if (!ok.includes(cmd)) throw new Error('nope'); return ''; };
  assert.equal(detectEngine({ exec: only(['docker', 'podman']) }), 'docker');
  assert.deepEqual(tried, [['docker', 'version']]);
  assert.equal(detectEngine({ exec: only(['podman']) }), 'podman');
  assert.equal(detectEngine({ exec: only([]) }), null);
  assert.equal(detectEngine({ exec: only(['docker', 'podman']), preferred: 'podman' }), 'podman');
  assert.equal(detectEngine({ exec: only(['docker']), preferred: 'podman' }), null);
});

test('validateStudyInContainer takes status from the marker line', () => {
  const run = (out) => validateStudyInContainer(fixtures, { engine: 'docker', exec: () => out });
  assert.deepEqual(run('ok\nSTF_VALIDATION: PASS\n'), { status: 'pass', output: 'ok\nSTF_VALIDATION: PASS' });
  assert.equal(run('bad row\nSTF_VALIDATION: FAIL\n').status, 'fail');
  assert.equal(run('STF_LOAD_ERROR: no study.yaml\n').status, 'load-error');
  assert.equal(run('STF_VALIDATION_ERROR: Can\'t subset elements that don\'t exist.\n').status, 'error');
});

test('an R error in geo inference or validate() is status error, exit 2, not a load-error', () => {
  const exec = () => { throw failing({ status: 2, stdout: 'STF_VALIDATION_ERROR: join failed\n', stderr: '' }); };
  const r = validateStudyInContainer(fixtures, { engine: 'docker', exec });
  assert.equal(r.status, 'error');
  assert.match(r.output, /STF_VALIDATION_ERROR: join failed/);
});

test('CLI: Result: error exits 2 (fake docker on PATH)', () => {
  const bin = mkdtempSync(join(tmpdir(), 'fake-engine-'));
  temps.push(bin);
  writeFileSync(join(bin, 'docker'), '#!/bin/sh\n[ "$1" = version ] && exit 0\necho "STF_VALIDATION_ERROR: join failed"\nexit 2\n', { mode: 0o755 });
  const r = spawnSync('node', [cli, fixtures, '--engine', 'docker'], { encoding: 'utf8', env: { ...process.env, PATH: `${bin}:${process.env.PATH}` } });
  assert.equal(r.status, 2, r.stdout + r.stderr);
  assert.match(r.stdout, /^Result: error$/m);
});

test('a failing run still reports its marker, from stdout and stderr together', () => {
  const exec = () => { throw failing({ status: 1, stdout: '== entity: a ==\nSTF_VALIDATION: FAIL\n', stderr: 'warn' }); };
  const r = validateStudyInContainer(fixtures, { engine: 'docker', exec });
  assert.equal(r.status, 'fail');
  assert.match(r.output, /entity: a[\s\S]*FAIL[\s\S]*warn/);
});

test('a non-zero exit with no marker (the container never got to load the study) is a load-error carrying the output', () => {
  const exec = () => { throw failing({ status: 125, stdout: '', stderr: 'image not known' }); };
  const r = validateStudyInContainer(fixtures, { engine: 'podman', exec });
  assert.equal(r.status, 'load-error');
  assert.match(r.output, /image not known/);
});

test('validateStudyInContainer runs the engine with containerArgs', () => {
  let call;
  validateStudyInContainer(fixtures, { engine: 'docker', exec: (cmd, args) => { call = [cmd, args]; return 'STF_VALIDATION: PASS'; } });
  assert.equal(call[0], 'docker');
  assert.deepEqual(call[1], containerArgs('docker', fixtures, script));
});

test('CLI without a directory prints usage and fails', () => {
  const r = spawnSync('node', [cli], { encoding: 'utf8' });
  assert.equal(r.status, 1);
  assert.match(r.stderr, /Usage: validate-stf-in-container\.js/);
});

// Opt-in: needs a container engine and the pinned image already present locally.
const integration = process.env.STF_CONTAINER_TESTS === '1';
const copyOf = (dataset) => {
  const dir = mkdtempSync(join(tmpdir(), 'stf-container-'));
  temps.push(dir);
  cpSync(join(fixtures, dataset, 'expected'), dir, { recursive: true });
  return dir;
};
const run = (dir) => validateStudyInContainer(dir);

for (const dataset of ['clinical-epi', 'mosquito', 'coffee-shops']) {
  test(`container: golden ${dataset} passes baseline+eda`, { skip: !integration }, () => {
    const r = run(join(fixtures, dataset, 'expected'));
    assert.equal(r.status, 'pass', r.output);
  });
}

test('container: an orphan child row does not pass', { skip: !integration }, () => {
  const dir = copyOf('mosquito');
  const tsv = join(dir, 'entity-assay.tsv');
  const lines = readFileSync(tsv, 'utf8').trimEnd().split('\n');
  const orphan = lines[1].split('\t');
  orphan[0] = 'NO_SUCH_SAMPLE'; // first column is the parent id
  orphan[1] = 'A_ORPHAN';
  writeFileSync(tsv, lines.concat(orphan.join('\t')).join('\n') + '\n');
  const r = run(dir);
  assert.notEqual(r.status, 'pass', r.output);
});

test('container: a parent ID column under another name is an R error in validate(), status error', { skip: !integration }, () => {
  const dir = copyOf('clinical-epi');
  const tsv = join(dir, 'entity-household.tsv');
  writeFileSync(tsv, readFileSync(tsv, 'utf8').replace(/^village_id\t/, 'village_id_2\t'));
  const yaml = join(dir, 'entity-household.yaml');
  writeFileSync(yaml, readFileSync(yaml, 'utf8').replace('- id_column: village_id\n', '- id_column: village_id_2\n'));
  assert.ok(checkStf(dir).errors.some((e) => /village_id_2 refers to village/.test(e)));
  const r = run(dir);
  assert.equal(r.status, 'error', r.output);
  assert.match(r.output, /^STF_VALIDATION_ERROR:/m);
});

test('container: stripped optional metadata still loads', { skip: !integration }, () => {
  const dir = copyOf('mosquito');
  for (const e of ['site', 'collection', 'sample', 'assay']) {
    const p = join(dir, `entity-${e}.yaml`);
    const text = readFileSync(p, 'utf8');
    const kept = text.slice(0, text.includes('\ncategories:') ? text.indexOf('\ncategories:') : undefined)
      .split('\n').filter((l) => !/^\s+(definition|unit|parent_category):/.test(l));
    writeFileSync(p, kept.join('\n') + '\n');
  }
  assert.deepEqual(checkStf(dir).errors, []);
  const r = run(dir);
  assert.notEqual(r.status, 'load-error', r.output);
});

test('container: geohash columns already present do not break validation (geo step is idempotent)', { skip: !integration }, () => {
  const dir = copyOf('mosquito');
  const names = [1, 2, 3, 4, 5, 6].map((n) => `geohash_${n}`);
  const tsv = join(dir, 'entity-site.tsv'); // the geo entity: latitude and longitude
  const lines = readFileSync(tsv, 'utf8').trimEnd().split('\n');
  const rows = lines.map((l, i) => (i === 0 ? [l, ...names] : [l, ...names.map((_, k) => 'abcdef'.slice(0, k + 1))]).join('\t'));
  writeFileSync(tsv, rows.join('\n') + '\n');
  const yamlPath = join(dir, 'entity-site.yaml');
  const yaml = readFileSync(yamlPath, 'utf8');
  const vars = names.map((n) => `  - variable: ${n}\n    provider_label:\n      - ${n}\n    display_name: ${n}\n    data_type: string\n    data_shape: categorical\n`).join('');
  assert.ok(yaml.includes('\nvariables:\n'));
  writeFileSync(yamlPath, yaml.replace(/(\nvariables:\n(?:  .*\n|\n)*?)(?=\S|$)/, (m) => m.trimEnd() + '\n' + vars));
  const r = run(dir);
  assert.equal(r.status, 'pass', r.output);
});
