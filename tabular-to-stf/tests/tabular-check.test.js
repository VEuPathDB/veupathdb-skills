import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, cpSync, readFileSync, writeFileSync, rmSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { spawnSync } from 'node:child_process';
import { checkStf, geohashWarning } from '../scripts/lib/tabular/check.js';

const fixtures = new URL('./fixtures/tabular/', import.meta.url).pathname;
const cli = new URL('../scripts/check-stf.js', import.meta.url).pathname;
const DATASETS = ['clinical-epi', 'mosquito', 'coffee-shops'];

const temps = [];
after(() => { for (const d of temps) rmSync(d, { recursive: true, force: true }); });

// Copy a golden expected/ dir to a temp dir.
function copyOf(dataset) {
  const dir = mkdtempSync(join(tmpdir(), 'check-stf-'));
  temps.push(dir);
  cpSync(join(fixtures, dataset, 'expected'), dir, { recursive: true });
  return dir;
}
const read = (dir, f) => readFileSync(join(dir, f), 'utf8');
const write = (dir, f, text) => writeFileSync(join(dir, f), text);
// Replace the first occurrence of `from`; fail loudly if the fixture changed under us.
function edit(dir, f, from, to) {
  const text = read(dir, f);
  assert.ok(text.includes(from), `${f} has no ${JSON.stringify(from)}`);
  write(dir, f, text.replace(from, to));
}
// Append a column to an entity TSV (value `fill` on every row) and a variable block to its YAML.
function addColumn(dir, entity, name, fill, yamlLines) {
  const lines = read(dir, `entity-${entity}.tsv`).split('\n');
  const out = lines.map((l, i) => (l === '' ? l : `${l}\t${i === 0 ? name : fill}`));
  write(dir, `entity-${entity}.tsv`, out.join('\n'));
  edit(dir, `entity-${entity}.yaml`, '\ncategories', `  - variable: ${name}\n${yamlLines}\n\ncategories`);
}
const NUM = '    display_name: X\n    data_type: number\n    data_shape: continuous';
const has = (list, re) => list.some((m) => re.test(m));

for (const d of DATASETS) {
  test(`golden fixture ${d} passes with no errors`, () => {
    const r = checkStf(join(fixtures, d, 'expected'));
    assert.deepEqual(r.errors, []);
  });
}

test('orphan child row is an error naming file and row ID', () => {
  const dir = copyOf('clinical-epi');
  edit(dir, 'entity-participant.tsv', 'H001\tP001', 'H999\tP001');
  const { errors } = checkStf(dir);
  assert.ok(has(errors, /entity-participant\.tsv.*P001.*H999.*household/), errors.join('\n'));
});

test('duplicate own ID is an error', () => {
  const dir = copyOf('clinical-epi');
  edit(dir, 'entity-participant.tsv', '\tP002\t', '\tP001\t');
  assert.ok(has(checkStf(dir).errors, /entity-participant\.tsv.*P001.*duplicate/i));
});

test('empty own ID is an error', () => {
  const dir = copyOf('clinical-epi');
  edit(dir, 'entity-participant.tsv', '\tP002\t', '\t\t');
  assert.ok(has(checkStf(dir).errors, /entity-participant\.tsv.*empty/i));
});

test('TSV column missing from the YAML is an error', () => {
  const dir = copyOf('mosquito');
  const lines = read(dir, 'entity-collection.tsv').split('\n');
  write(dir, 'entity-collection.tsv', lines.map((l, i) => (l === '' ? l : `${l}\t${i === 0 ? 'extra_col' : 'x'}`)).join('\n'));
  assert.ok(has(checkStf(dir).errors, /entity-collection\.tsv.*extra_col.*not in entity-collection\.yaml/));
});

test('YAML variable missing from the TSV is an error', () => {
  const dir = copyOf('mosquito');
  edit(dir, 'entity-collection.yaml', '\ncategories', '  - variable: ghost\n    display_name: Ghost\n    data_type: string\n    data_shape: categorical\n\ncategories');
  assert.ok(has(checkStf(dir).errors, /entity-collection\.yaml.*ghost.*not in entity-collection\.tsv/));
});

test('bad data_type is an error', () => {
  const dir = copyOf('mosquito');
  edit(dir, 'entity-collection.yaml', 'data_type: integer', 'data_type: integr');
  assert.ok(has(checkStf(dir).errors, /entity-collection\.yaml.*trap_nights.*data_type.*integr/));
});

test('bad data_shape, display_type, hidden are errors; ordinal needs ordinal_levels', () => {
  const dir = copyOf('mosquito');
  edit(dir, 'entity-collection.yaml', 'data_shape: categorical', 'data_shape: ordinal\n    display_type: sideways\n    hidden:\n      - nowhere');
  const { errors } = checkStf(dir);
  assert.ok(has(errors, /display_type.*sideways/), errors.join('\n'));
  assert.ok(has(errors, /hidden.*nowhere/));
  assert.ok(has(errors, /ordinal.*ordinal_levels/));
});

test('2023-02-30 in a date column is an error naming the row ID', () => {
  const dir = copyOf('mosquito');
  edit(dir, 'entity-collection.tsv', '2022-07-04', '2023-02-30');
  assert.ok(has(checkStf(dir).errors, /entity-collection\.tsv.*C001.*collection_date.*2023-02-30/));
});

test('non-numeric value in a number column, and out-of-range coordinates, are errors', () => {
  const dir = copyOf('mosquito');
  edit(dir, 'entity-site.tsv', '11.1771', '91');
  edit(dir, 'entity-site.tsv', '-4.2979', '-181');
  edit(dir, 'entity-collection.tsv', '\t1\ton', '\tmany\ton');
  const { errors } = checkStf(dir);
  assert.ok(has(errors, /entity-site\.tsv.*BF01.*latitude.*91/), errors.join('\n'));
  assert.ok(has(errors, /entity-site\.tsv.*BF01.*longitude.*-181/));
  assert.ok(has(errors, /entity-collection\.tsv.*C001.*trap_nights.*many/));
});

test('ordinal value outside ordinal_levels is an error', () => {
  const dir = copyOf('mosquito');
  edit(dir, 'entity-collection.yaml', 'data_shape: categorical\n    vocabulary_order:', 'data_shape: ordinal\n    ordinal_levels:\n      - low\n    vocabulary_order:');
  assert.ok(has(checkStf(dir).errors, /entity-collection\.tsv.*trap_light.*"on".*ordinal_levels/));
});

test('parent_category naming nothing is an error', () => {
  const dir = copyOf('clinical-epi');
  edit(dir, 'entity-participant.yaml', 'parent_category: demographics', 'parent_category: nothing');
  assert.ok(has(checkStf(dir).errors, /entity-participant\.yaml.*parent_category.*nothing/));
});

test('category cycle is an error', () => {
  const dir = copyOf('clinical-epi');
  edit(dir, 'entity-participant.yaml', '    definition: Clinical history and measurements at enrolment.\n', '    definition: Clinical history and measurements at enrolment.\n    parent_category: anthropometry\n');
  assert.ok(has(checkStf(dir).errors, /entity-participant\.yaml.*cycle/i));
});

test('duplicate variable or category name is an error', () => {
  const dir = copyOf('clinical-epi');
  edit(dir, 'entity-participant.yaml', '  - category: behaviour', '  - category: sex');
  assert.ok(has(checkStf(dir).errors, /entity-participant\.yaml.*duplicate.*sex/i));
});

test('entity_level -2 on an immediate parent is an error', () => {
  const dir = copyOf('clinical-epi');
  edit(dir, 'entity-participant.yaml', 'entity_level: -1', 'entity_level: -2');
  assert.ok(has(checkStf(dir).errors, /entity-participant\.yaml.*entity_level.*-2/));
});

test('two latitude-like columns are an error', () => {
  const dir = copyOf('mosquito');
  addColumn(dir, 'site', 'lat', '1', NUM);
  assert.ok(has(checkStf(dir).errors, /entity-site\.yaml.*more than one latitude/i));
});

test('wrong latitude stable_id is an error', () => {
  const dir = copyOf('mosquito');
  edit(dir, 'entity-site.yaml', 'OBI_0001620', 'OBI_9');
  assert.ok(has(checkStf(dir).errors, /entity-site\.yaml.*latitude.*stable_id.*OBI_0001620/));
});

test('a lone latitude is a warning, not an error', () => {
  const dir = copyOf('clinical-epi');
  addColumn(dir, 'household', 'latitude', '1', `${NUM}\n    stable_id: OBI_0001620\n    display_type: latitude`);
  const r = checkStf(dir);
  assert.deepEqual(r.errors, []);
  assert.ok(has(r.warnings, /entity-household\.yaml.*latitude.*mislabelled/i), r.warnings.join('\n'));
});

test('a name the inference accepts but the validator does not is a warning', () => {
  const dir = copyOf('clinical-epi');
  addColumn(dir, 'village', 'gps_lat', '1', NUM);
  const r = checkStf(dir);
  assert.deepEqual(r.errors, []);
  assert.ok(has(r.warnings, /entity-village\.yaml.*gps_lat.*inference.*validator/i), r.warnings.join('\n'));
});

test('missing study.yaml entity file is an error', () => {
  const dir = copyOf('mosquito');
  rmSync(join(dir, 'entity-assay.yaml'));
  assert.ok(has(checkStf(dir).errors, /entity-assay\.yaml.*missing/));
});

test('missing study.yaml is an error', () => {
  const dir = copyOf('mosquito');
  rmSync(join(dir, 'study.yaml'));
  assert.ok(has(checkStf(dir).errors, /study\.yaml.*missing/));
});

test('STF-lite (no YAML) is not supported', () => {
  const dir = copyOf('mosquito');
  for (const n of ['site', 'collection', 'sample', 'assay']) rmSync(join(dir, `entity-${n}.yaml`));
  rmSync(join(dir, 'study.yaml'));
  assert.ok(has(checkStf(dir).errors, /STF-lite not supported; validate in mode 2/));
});

test('transposed TSV is reported as such', () => {
  const dir = copyOf('mosquito');
  edit(dir, 'entity-site.tsv', 'site_id \\\\ Descriptors', 'Descriptors \\\\ site_id');
  assert.ok(has(checkStf(dir).errors, /entity-site\.tsv.*transposed or malformed TSV.*validate in mode 2/));
});

test('a row with the wrong cell count is an error', () => {
  const dir = copyOf('mosquito');
  edit(dir, 'entity-site.tsv', 'BF01\t0123\t', 'BF01\t');
  assert.ok(has(checkStf(dir).errors, /entity-site\.tsv.*cells/));
});

test('a column name that is not a plain identifier is a warning', () => {
  const dir = copyOf('mosquito');
  edit(dir, 'entity-site.tsv', '\thabitat', '\thabitat type');
  edit(dir, 'entity-site.yaml', 'variable: habitat', 'variable: habitat type');
  const r = checkStf(dir);
  assert.deepEqual(r.errors, []);
  assert.ok(has(r.warnings, /habitat type/));
});

test('adding geohash_1 gives a warning only', () => {
  const dir = copyOf('mosquito');
  addColumn(dir, 'site', 'geohash_1', 'a', '    display_name: G\n    data_type: string\n    data_shape: categorical');
  const r = checkStf(dir);
  assert.deepEqual(r.errors, []);
  assert.ok(has(r.warnings, /entity-site\.yaml.*geohash columns present; they will be recomputed by infer_geo_variables_for_eda\(\)/), r.warnings.join('\n'));
});

test('geohash warning wording depends on the study-wrangler version, compared numerically', () => {
  assert.match(geohashWarning('1.0.52'), /drop them before mode 2 validation.*<1\.0\.53 would duplicate them/);
  assert.match(geohashWarning('1.0.9'), /drop them/);
  assert.match(geohashWarning('1.0.53'), /recomputed/);
  assert.match(geohashWarning('1.0.100'), /recomputed/);
  assert.match(geohashWarning('1.1.0'), /recomputed/);
});

test('a childless parent row is fine', () => {
  const dir = copyOf('clinical-epi');
  const text = read(dir, 'entity-household.tsv').trimEnd().split('\n');
  const cols = text[0].split('\t').length;
  write(dir, 'entity-household.tsv', `${text.join('\n')}\n${['V01', 'H999', ...Array(cols - 2).fill('')].join('\t')}\n`);
  assert.deepEqual(checkStf(dir).errors, []);
});

test('a grandchild listing both ancestors passes; a wrong grandparent value fails', () => {
  const dir = copyOf('clinical-epi');
  const parents = new Map(read(dir, 'entity-participant.tsv').trimEnd().split('\n').slice(1).map((l) => l.split('\t')).map((c) => [c[1], c[0]]));
  const rows = read(dir, 'entity-sample.tsv').trimEnd().split('\n');
  const withHousehold = rows.map((l, i) => (i === 0 ? `household_id\t${l}` : `${parents.get(l.split('\t')[0])}\t${l}`));
  write(dir, 'entity-sample.tsv', `${withHousehold.join('\n')}\n`);
  edit(dir, 'entity-sample.yaml', 'id_columns:\n', 'id_columns:\n  - id_column: household_id\n    entity_name: household\n    entity_level: -2\n');
  assert.deepEqual(checkStf(dir).errors, []);
  withHousehold[1] = withHousehold[1].replace(/^[^\t]+/, 'H999');
  write(dir, 'entity-sample.tsv', `${withHousehold.join('\n')}\n`);
  assert.ok(has(checkStf(dir).errors, /entity-sample\.tsv.*H999.*household/));
});

test('an ancestor id_column named other than the ancestor\'s own ID column is an error', () => {
  const dir = copyOf('clinical-epi');
  edit(dir, 'entity-household.tsv', 'village_id\thousehold_id', 'village_id_2\thousehold_id');
  edit(dir, 'entity-household.yaml', '- id_column: village_id\n', '- id_column: village_id_2\n');
  const { errors } = checkStf(dir);
  assert.ok(has(errors, /entity-household\.yaml: id_column village_id_2 refers to village, whose own ID column is village_id/), errors.join('\n'));
});

test('wrong ancestor level for a grandparent is an error', () => {
  const dir = copyOf('clinical-epi');
  edit(dir, 'entity-sample.yaml', 'id_columns:\n', 'id_columns:\n  - id_column: household_id\n    entity_name: household\n    entity_level: -3\n');
  assert.ok(has(checkStf(dir).errors, /entity-sample\.yaml.*household.*entity_level.*-3.*-2/));
});

test('a missing raw-data path mentioned in the notes is a warning', () => {
  const dir = copyOf('mosquito');
  rmSync(join(dir, 'raw-data', 'samples.tsv'));
  const r = checkStf(dir);
  assert.deepEqual(r.errors, []);
  assert.ok(has(r.warnings, /curation-notes\.md.*raw-data\/samples\.tsv/));
});

test('raw-data/ and unlisted files are ignored', () => {
  const dir = copyOf('mosquito');
  write(dir, 'entity-stray.tsv', 'junk');
  write(dir, 'entity-stray.yaml', 'junk: [');
  assert.deepEqual(checkStf(dir).errors, []);
});

test('CLI: exits 0 and prints nothing bad on a good dir; exits 1 with ERROR lines on a bad one; --json', () => {
  const good = spawnSync(cli, [join(fixtures, 'mosquito', 'expected')], { encoding: 'utf8' });
  assert.equal(good.status, 0, good.stderr);
  const dir = copyOf('mosquito');
  edit(dir, 'entity-collection.yaml', 'data_type: integer', 'data_type: integr');
  const bad = spawnSync(cli, [dir], { encoding: 'utf8' });
  assert.equal(bad.status, 1);
  assert.match(bad.stdout, /^ERROR: entity-collection\.yaml/m);
  const json = spawnSync(cli, [dir, '--json'], { encoding: 'utf8' });
  assert.equal(json.status, 1);
  const parsed = JSON.parse(json.stdout);
  assert.ok(parsed.errors.length > 0 && Array.isArray(parsed.warnings));
  assert.equal(spawnSync(cli, [join(dir, 'nope')], { encoding: 'utf8' }).status, 1);
});
