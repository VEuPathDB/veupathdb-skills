import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, cpSync, readFileSync, writeFileSync, readdirSync, existsSync, statSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { execFileSync } from 'node:child_process';
import { renderStf, RenderError } from '../scripts/lib/tabular/render.js';
import { renderNotes } from '../scripts/lib/tabular/notes.js';
import { validateSpec } from '../scripts/lib/tabular/spec.js';
import { readTable } from '../scripts/lib/tabular/read-table.js';
import { parseYaml } from '../scripts/lib/yaml-lite.js';

const fixtures = new URL('./fixtures/tabular/', import.meta.url).pathname;
const cli = new URL('../scripts/render-stf.js', import.meta.url).pathname;
const DATASETS = ['clinical-epi', 'mosquito', 'coffee-shops'];

// Minimal one- or two-entity spec; `variables` are the root entity's.
function spec(variables, extra = {}) {
  return {
    specVersion: 1,
    study: { name: 'Test study' },
    inputDir: '/in',
    entities: [{ name: 'p', displayName: 'P', displayNamePlural: 'Ps', file: 'p.csv', idColumn: 'id', variables, ...extra }],
    transforms: [],
  };
}
const table = (headers, ...rows) => ({ headers, rows });
const one = (t) => new Map([['p', t]]);
const lines = (text) => text.split('\n');

function loadFixture(ds) {
  const s = JSON.parse(readFileSync(join(fixtures, ds, 'spec.json'), 'utf8'));
  const tables = new Map(s.entities.map((e) => {
    const { headers, rows } = readTable(join(fixtures, ds, s.inputDir, e.file));
    return [e.name, { headers, rows }];
  }));
  return { spec: s, tables };
}

// Names the first file and line where `files` and the directory differ.
function assertFilesMatchDir(files, dir) {
  for (const [name, text] of Object.entries(files)) {
    const path = join(dir, name);
    assert.ok(existsSync(path), `missing golden file ${path}`);
    const want = lines(readFileSync(path, 'utf8'));
    const got = lines(text);
    for (let i = 0; i < Math.max(want.length, got.length); i++) {
      assert.equal(got[i], want[i], `${name} line ${i + 1} differs`);
    }
  }
}

function throwsRender(fn, pattern) {
  assert.throws(fn, (err) => {
    assert.ok(err instanceof RenderError, `expected RenderError, got ${err}`);
    assert.ok(Array.isArray(err.messages));
    assert.match(err.messages.join('\n'), pattern);
    return true;
  });
}

test('auto names come from headers; provider_label keeps the header', () => {
  const { files } = renderStf(spec([{ column: 'Age (years)' }, { column: 'Hb (g/dL)' }]),
    one(table(['id', 'Age (years)', 'Hb (g/dL)'], ['P1', '34', '12.5'])));
  assert.equal(lines(files['entity-p.tsv'])[0], 'id \\\\ Descriptors\tage_years\thb_g_dl');
  const y = parseYaml(files['entity-p.yaml']);
  assert.deepEqual(y.variables.map((v) => [v.variable, v.provider_label]), [['age_years', ['Age (years)']], ['hb_g_dl', ['Hb (g/dL)']]]);
  assert.deepEqual(y.variables.map((v) => [v.data_type, v.data_shape]), [['integer', 'continuous'], ['number', 'continuous']]);
});

test('explicit name and idName are used', () => {
  const { files } = renderStf(spec([{ column: 'Age (years)', name: 'age' }], { idName: 'person_id' }),
    one(table(['id', 'Age (years)'], ['P1', '34'])));
  assert.equal(lines(files['entity-p.tsv'])[0], 'person_id \\\\ Descriptors\tage');
  assert.equal(parseYaml(files['entity-p.yaml']).id_columns[0].id_column, 'person_id');
});

test('an explicit name of 2nd fails validateSpec', () => {
  assert.ok(validateSpec(spec([{ column: 'x', name: '2nd' }])).some((e) => /invalid column name "2nd"/.test(e)));
  throwsRender(() => renderStf(spec([{ column: 'x', name: '2nd' }]), one(table(['id', 'x'], ['P1', '1']))), /2nd/);
});

test('clashing explicit names fail; clashing auto names are suffixed', () => {
  throwsRender(() => renderStf(spec([{ column: 'a', name: 'z' }, { column: 'b', name: 'z' }]), one(table(['id', 'a', 'b'], ['P1', '1', '2']))),
    /p: output column name "z" is used by both "a" and "b"/);
  const { files } = renderStf(spec([{ column: 'A b' }, { column: 'a_b', name: 'a_b' }, { column: 'a-b' }]),
    one(table(['id', 'A b', 'a_b', 'a-b'], ['P1', '1', '2', '3'])));
  assert.equal(lines(files['entity-p.tsv'])[0], 'id \\\\ Descriptors\ta_b_2\ta_b\ta_b_3');
});

test('a child lists the parent ID first, under the parent\'s output ID name', () => {
  const s = spec([{ column: 'x' }], { idName: 'hh' });
  s.entities.push({ name: 'c', displayName: 'C', displayNamePlural: 'Cs', file: 'c.csv', idColumn: 'cid', parent: 'p', parentColumn: 'household', variables: [{ column: 'hh' }] });
  const tables = new Map([['p', table(['id', 'x'], ['H1', 'a'])], ['c', table(['cid', 'household', 'hh'], ['C1', 'H1', 'y'])]]);
  const { files } = renderStf(s, tables);
  assert.equal(files['study.yaml'], 'name: Test study\nentities:\n  - p\n  - c\n');
  assert.deepEqual(lines(files['entity-c.tsv']), ['hh\tcid \\\\ Descriptors\thh_2', 'H1\tC1\ty', '']);
  const y = parseYaml(files['entity-c.yaml']);
  assert.deepEqual(y.id_columns, [
    { id_column: 'hh', entity_name: 'p', entity_level: -1, provider_label: ['household'] },
    { id_column: 'cid', entity_name: 'c', provider_label: ['cid'] },
  ]);
  assert.match(files['entity-c.yaml'], /\ncategories: \[\]\n$/);
});

test('an explicit child name or idName equal to the parent\'s ID name is an error; the parent ID is never renamed', () => {
  const build = (child) => {
    const s = spec([{ column: 'x' }], { idName: 'hh' });
    s.entities.push({ name: 'c', displayName: 'C', displayNamePlural: 'Cs', file: 'c.csv', idColumn: 'cid', parent: 'p', parentColumn: 'household', variables: [{ column: 'v' }], ...child });
    return s;
  };
  const tables = new Map([['p', table(['id', 'x'], ['H1', 'a'])], ['c', table(['cid', 'household', 'v'], ['C1', 'H1', 'y'])]]);
  throwsRender(() => renderStf(build({ variables: [{ column: 'v', name: 'hh' }] }), tables),
    /c: output column name "hh" for column "v" is the ID column name of parent entity "p"/);
  throwsRender(() => renderStf(build({ idName: 'hh' }), tables),
    /c: output column name "hh" for column "cid" is the ID column name of parent entity "p"/);
});

test('an unaccounted column fails the render', () => {
  throwsRender(() => renderStf(spec([{ column: 'a' }]), one(table(['id', 'a', 'b c'], ['P1', '1', '2']))), /unaccounted column p\.b c/);
});

test('a declared type that does not parse lists the bad values with row IDs', () => {
  throwsRender(() => renderStf(spec([{ column: 'n', dataType: 'integer' }]), one(table(['id', 'n'], ['P1', '1'], ['P2', 'abc'], ['P3', '2.5'], ['P4', '']))),
    /p\.n: declared integer but 2 values do not parse: "abc" \(P2\), "2\.5" \(P3\)/);
  throwsRender(() => renderStf(spec([{ column: 'd', dataType: 'date' }]), one(table(['id', 'd'], ['P1', '2023-02-30']))), /"2023-02-30" \(P1\)/);
});

test('a tab or line break in a value fails, naming entity, column and row ID', () => {
  throwsRender(() => renderStf(spec([{ column: 'a' }]), one(table(['id', 'a'], ['P1', 'ok'], ['P2', 'x\ty']))), /p\.a: value in row P2 contains a tab or line break/);
  throwsRender(() => renderStf(spec([{ column: 'a' }]), one(table(['id', 'a'], ['P1', 'x\ny']))), /row P1/);
});

const geoSpec = (variables) => spec(variables, { geo: { latitude: 'gps_lat', longitude: 'gps_lon' } });
const geoTable = (extraHeaders = [], extra = []) => one(table(['id', 'gps_lat', 'gps_lon', ...extraHeaders], ['P1', '1.5', '-30.25', ...extra]));

test('geo columns are renamed when either rule fails and get GEO metadata', () => {
  const { files, log } = renderStf(geoSpec([{ column: 'gps_lat' }, { column: 'gps_lon' }]), geoTable());
  assert.ok(Array.isArray(log));
  assert.equal(lines(files['entity-p.tsv'])[0], 'id \\\\ Descriptors\tlatitude\tlongitude');
  const [lat, lon] = parseYaml(files['entity-p.yaml']).variables;
  assert.deepEqual([lat.stable_id, lat.data_type, lat.data_shape, lat.display_type], ['OBI_0001620', 'number', 'continuous', 'latitude']);
  assert.deepEqual([lon.stable_id, lon.data_type, lon.data_shape, lon.display_type], ['OBI_0001621', 'longitude', 'continuous', 'longitude']);
  assert.match(files['curation-notes.md'], /Before `eda` validation or export, run `map_entities\(study, infer_geo_variables_for_eda\)`/);
  const ok = renderStf(spec([{ column: 'Lat' }, { column: 'Long' }], { geo: { latitude: 'Lat', longitude: 'Long' } }),
    one(table(['id', 'Lat', 'Long'], ['P1', '1', '2'])));
  assert.equal(lines(ok.files['entity-p.tsv'])[0], 'id \\\\ Descriptors\tlat\tlong');
});

test('a stray coordinate-like column in a geo entity is an error suggesting the fix', () => {
  throwsRender(() => renderStf(geoSpec([{ column: 'gps_lat' }, { column: 'gps_lon' }, { column: 'long_term_resident' }]), geoTable(['long_term_resident'], ['Yes'])),
    /p\.long_term_resident: name "long_term_resident" looks like a longitude.*rename-column/);
  throwsRender(() => renderStf(geoSpec([{ column: 'gps_lat' }, { column: 'gps_lon' }, { column: 'Long-term illness', name: 'chronic_illness' }]), geoTable(['Long-term illness'], ['No'])),
    /p\.chronic_illness: provider_label "Long-term illness" looks like a longitude.*providerLabel/);
});

test('providerLabel overrides the header and is logged under Decisions', () => {
  const { files } = renderStf(geoSpec([{ column: 'gps_lat' }, { column: 'gps_lon' }, { column: 'Long-term illness', name: 'chronic_illness', providerLabel: 'Chronic illness' }]),
    geoTable(['Long-term illness'], ['No']));
  assert.deepEqual(parseYaml(files['entity-p.yaml']).variables[2].provider_label, ['Chronic illness']);
  const decisions = files['curation-notes.md'].split('## Decisions and answers')[1].split('## Validation')[0];
  assert.match(decisions, /`p\.chronic_illness`: provider_label set to "Chronic illness" \(original header "Long-term illness"\)/);
});

test('a non-geo entity with two coordinate-like columns fails; one is allowed', () => {
  throwsRender(() => renderStf(spec([{ column: 'lat' }, { column: 'latitude' }]), one(table(['id', 'lat', 'latitude'], ['P1', '1', '2']))),
    /p: 2 columns look like coordinates \(lat, latitude\)/);
  assert.doesNotThrow(() => renderStf(spec([{ column: 'lat' }]), one(table(['id', 'lat'], ['P1', '1']))));
});

test('IDs and codes with leading zeros stay as written, as strings', () => {
  const { files } = renderStf(spec([{ column: 'code' }]), one(table(['id', 'code'], ['0123', '0007'], ['0456', '12'])));
  assert.deepEqual(lines(files['entity-p.tsv']).slice(1), ['0123\t0007', '0456\t12', '']);
  assert.equal(parseYaml(files['entity-p.yaml']).variables[0].data_type, 'string');
});

test('renderNotes lists sections in order; Validation defaults to not run', () => {
  const s = spec([{ column: 'a' }]);
  s.transforms = [{ op: 'trim', entity: 'p', approval: 'auto', reason: 'spaces' }];
  const notes = renderNotes(s, [{ index: 0, op: 'trim', entity: 'p', approval: 'auto', cellsChanged: 3 }]);
  const heads = notes.split('\n').filter((l) => l.startsWith('## '));
  assert.deepEqual(heads, ['## Study', '## Entity tree', '## Routine normalisation', '## Data changes', '## Flagged, not changed', '## Decisions and answers', '## Validation']);
  assert.match(notes, /## Validation\n\nNot run \(mode 1\)\n/);
  assert.match(notes, /`p` \(all columns\): trim whitespace, 3 cells changed\. Reason: spaces/);
});

test('renderNotes lists row IDs for user value changes, capped at 10, and not for auto ones', () => {
  const s = spec([{ column: 'a' }]);
  s.transforms = [
    { op: 'map-values', entity: 'p', column: 'a', map: { x: 'y' }, approval: 'user', reason: 'typo' },
    { op: 'map-values', entity: 'p', column: 'a', map: { z: 'y' }, approval: 'user', reason: 'many' },
    { op: 'trim', entity: 'p', approval: 'auto', reason: 'spaces' },
  ];
  const ids = Array.from({ length: 13 }, (_, i) => `R${i + 1}`);
  const notes = renderNotes(s, [
    { index: 0, op: 'map-values', entity: 'p', column: 'a', approval: 'user', cellsChanged: 1, ids: ['P7'] },
    { index: 1, op: 'map-values', entity: 'p', column: 'a', approval: 'user', cellsChanged: 13, ids },
    { index: 2, op: 'trim', entity: 'p', approval: 'auto', cellsChanged: 2, ids: ['Q1', 'Q2'] },
  ]);
  assert.match(notes, /`p\.a`: "x" → "y", 1 cell changed \(row P7\)\. Reason: typo/);
  assert.match(notes, /13 cells changed \(rows R1, R2, R3, R4, R5, R6, R7, R8, R9, R10 and 3 more\)\. Reason: many/);
  assert.match(notes, /trim whitespace, 2 cells changed\. Reason: spaces/);
  assert.doesNotMatch(notes, /Q1/);
});

for (const ds of DATASETS) {
  test(`golden: ${ds} renders byte for byte as expected/`, () => {
    const { spec: s, tables } = loadFixture(ds);
    const { files } = renderStf(s, tables);
    const names = Object.keys(files).sort();
    assert.deepEqual(names, ['curation-notes.md', 'study.yaml', ...s.entities.flatMap((e) => [`entity-${e.name}.tsv`, `entity-${e.name}.yaml`])].sort());
    const expected = join(fixtures, ds, 'expected');
    assertFilesMatchDir(files, expected);
    const onDisk = readdirSync(expected).filter((f) => !['raw-data', 'curation-spec.json'].includes(f)).sort();
    assert.deepEqual(onDisk, names);
  });

  test(`golden: ${ds} YAML round-trips display names and definitions`, () => {
    const { spec: s, tables } = loadFixture(ds);
    const { files } = renderStf(s, tables);
    for (const e of s.entities) {
      const y = parseYaml(files[`entity-${e.name}.yaml`]);
      assert.equal(y.display_name, e.displayName);
      // Variables are written in spec order
      assert.equal(y.variables.length, e.variables.length);
      for (const [i, v] of e.variables.entries()) {
        const got = y.variables[i];
        assert.equal(got.display_name, v.displayName);
        assert.equal(got.definition ?? undefined, v.definition);
        if (v.vocabularyOrder) assert.deepEqual(got.vocabulary_order, v.vocabularyOrder);
        if (v.ordinalLevels) assert.deepEqual(got.ordinal_levels, v.ordinalLevels);
      }
      assert.deepEqual((y.categories || []).map((c) => [c.category, c.display_name, c.definition ?? undefined]),
        (e.categories || []).map((c) => [c.category, c.displayName, c.definition]));
    }
  });
}

// ---- CLI ----

const run = (args, opts = {}) => execFileSync('node', [cli, ...args], { stdio: 'pipe', encoding: 'utf8', ...opts });
const runFails = (args) => {
  try { run(args); } catch (err) { return { status: err.status, out: `${err.stdout}${err.stderr}` }; }
  assert.fail('expected the CLI to fail');
};

const temps = [];
after(() => { for (const d of temps) rmSync(d, { recursive: true, force: true }); });

// A copy of a fixture's inputs and spec in a temp dir, so tests can mutate them.
function scratch(ds = 'clinical-epi') {
  const root = mkdtempSync(join(tmpdir(), 'render-stf-'));
  temps.push(root);
  cpSync(join(fixtures, ds, 'inputs'), join(root, 'inputs'), { recursive: true });
  cpSync(join(fixtures, ds, 'spec.json'), join(root, 'spec.json'));
  return root;
}
const read = (p) => readFileSync(p);
const stfFiles = (dir) => readdirSync(dir).filter((f) => !['raw-data', 'curation-spec.json'].includes(f)).sort();

test('CLI: renders with raw-data/, a saved spec that re-renders from the folder alone', () => {
  const root = scratch();
  const out = join(root, 'out');
  const printed = run([join(root, 'spec.json'), out]);
  assert.match(printed, /study\.yaml/);
  const s = JSON.parse(readFileSync(join(root, 'spec.json'), 'utf8'));
  for (const f of [...s.entities.map((e) => e.file), ...s.extraFiles]) {
    assert.deepEqual(read(join(out, 'raw-data', f)), read(join(root, 'inputs', f)), `raw-data/${f}`);
  }
  const saved = JSON.parse(readFileSync(join(out, 'curation-spec.json'), 'utf8'));
  assert.equal(saved.inputDir, 'raw-data');
  assert.deepEqual({ ...saved, inputDir: s.inputDir }, s);
  assert.match(readFileSync(join(out, 'curation-notes.md'), 'utf8'), /`raw-data\/participants\.csv` \(16 rows\)/);
  assertFilesMatchDir(Object.fromEntries(stfFiles(join(fixtures, 'clinical-epi', 'expected')).map((f) => [f, readFileSync(join(fixtures, 'clinical-epi', 'expected', f), 'utf8')])), out);

  const before = Object.fromEntries(stfFiles(out).map((f) => [f, readFileSync(join(out, f), 'utf8')]));
  const copy = join(root, 'moved');
  cpSync(out, copy, { recursive: true });
  run([join(copy, 'curation-spec.json'), copy]);
  assertFilesMatchDir(before, copy);
  assert.deepEqual(stfFiles(copy), Object.keys(before).sort());
});

test('CLI: refuses a non-empty outDir without curation-spec.json, re-renders into one with it', () => {
  const root = scratch();
  const out = join(root, 'out');
  mkdirSync(out);
  writeFileSync(join(out, 'keep.txt'), 'mine');
  const r = runFails([join(root, 'spec.json'), out]);
  assert.equal(r.status, 1);
  assert.match(r.out, /not empty and has no curation-spec\.json/);
  const out2 = join(root, 'out2');
  run([join(root, 'spec.json'), out2]);
  run([join(root, 'spec.json'), out2]);
  assert.ok(existsSync(join(out2, 'study.yaml')));
});

test('CLI: a changed source file with the same name as a raw-data copy is refused', () => {
  const root = scratch();
  const out = join(root, 'out');
  run([join(root, 'spec.json'), out]);
  writeFileSync(join(root, 'inputs', 'villages.csv'), readFileSync(join(root, 'inputs', 'villages.csv'), 'utf8').replace('Kanyawegi', 'Kanyawegy'));
  const r = runFails([join(root, 'spec.json'), out]);
  assert.equal(r.status, 1);
  assert.match(r.out, /raw-data\/villages\.csv differs from .*villages\.csv/);
  assert.match(readFileSync(join(out, 'raw-data', 'villages.csv'), 'utf8'), /Kanyawegi/);
});

test('CLI: --no-raw-data copies nothing and keeps an absolute inputDir', () => {
  const root = scratch('mosquito');
  const out = join(root, 'out');
  run([join(root, 'spec.json'), out, '--no-raw-data']);
  assert.ok(!existsSync(join(out, 'raw-data')));
  const saved = JSON.parse(readFileSync(join(out, 'curation-spec.json'), 'utf8'));
  assert.equal(saved.inputDir, join(root, 'inputs'));
  assert.match(readFileSync(join(out, 'curation-notes.md'), 'utf8'), new RegExp(`\`${join(root, 'inputs', 'samples.tsv')}\` \\(15 rows\\)`));
  run([join(out, 'curation-spec.json'), out, '--no-raw-data']);
});

test('CLI: render errors exit 1 with the messages', () => {
  const root = scratch('mosquito');
  const s = JSON.parse(readFileSync(join(root, 'spec.json'), 'utf8'));
  s.entities[0].variables.pop();
  writeFileSync(join(root, 'spec.json'), JSON.stringify(s));
  const r = runFails([join(root, 'spec.json'), join(root, 'out')]);
  assert.equal(r.status, 1);
  assert.match(r.out, /unaccounted column site\.habitat/);
  assert.ok(!existsSync(join(root, 'out', 'study.yaml')));
});

test('CLI is executable', () => {
  assert.ok(statSync(cli).mode & 0o111);
});
