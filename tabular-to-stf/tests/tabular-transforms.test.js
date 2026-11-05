import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { applyTransforms } from '../scripts/lib/tabular/transforms.js';

const T = (op, extra) => ({ op, entity: 'p', reason: 'r', approval: 'user', ...extra });
const spec = (transforms, idColumn = 'id') => ({ entities: [{ name: 'p', idColumn }], transforms });
function tables() {
  return new Map([['p', { headers: ['id', 'age', 'note'], rows: [['P1', '80+', ' NA '], ['P2', '5', 'ok '], ['P3', '', 'NA']] }]]);
}
const run = (transforms, t = tables(), idColumn) => applyTransforms(t, spec(transforms, idColumn));

test('trim defaults to all columns and counts changed cells', () => {
  const { tables: out, log } = run([T('trim')]);
  assert.deepEqual(out.get('p').rows[0], ['P1', '80+', 'NA']);
  assert.equal(log[0].cellsChanged, 2);
  assert.equal(log[0].index, 0);
});

test('trim with columns', () => {
  const { tables: out, log } = run([T('trim', { columns: ['note'] })]);
  assert.equal(out.get('p').rows[1][2], 'ok');
  assert.equal(log[0].cellsChanged, 2);
});

test('blank-placeholders', () => {
  const { tables: out, log } = run([T('blank-placeholders', { values: ['NA'], columns: ['note'] })]);
  assert.equal(out.get('p').rows[2][2], '');
  assert.equal(out.get('p').rows[0][2], ' NA ');
  assert.equal(log[0].cellsChanged, 1);
});

test('map-values exact match only', () => {
  const { tables: out, log } = run([T('map-values', { column: 'age', map: { '80+': '80', '5': '5' } })]);
  assert.deepEqual(out.get('p').rows.map((r) => r[1]), ['80', '5', '']);
  assert.equal(log[0].cellsChanged, 1);
  assert.equal(log[0].column, 'age');
});

test('rename-column and drop-column', () => {
  const { tables: out } = run([T('rename-column', { from: 'age', to: 'years' }), T('drop-column', { column: 'note' })]);
  assert.deepEqual(out.get('p').headers, ['id', 'years']);
  assert.deepEqual(out.get('p').rows[0], ['P1', '80+']);
});

test('missing column error names entity, index and column', () => {
  assert.throws(() => run([T('trim'), T('drop-column', { column: 'zzz' })]), /p.*1.*zzz|zzz/s);
  assert.throws(() => run([T('drop-column', { column: 'zzz' })]), (e) => /entity "p"/.test(e.message) && /transforms\[0\]/.test(e.message) && /zzz/.test(e.message));
});

test('proposed and rejected are skipped but logged', () => {
  const { tables: out, log } = run([
    T('drop-column', { column: 'note', approval: 'proposed' }),
    T('drop-column', { column: 'age', approval: 'rejected', instead: 'x' }),
  ]);
  assert.deepEqual(out.get('p').headers, ['id', 'age', 'note']);
  assert.deepEqual(log.map((l) => [l.index, l.approval, l.cellsChanged]), [[0, 'proposed', 0], [1, 'rejected', 0]]);
});

test('replace-cells applies by row ID', () => {
  const { tables: out, log } = run([T('replace-cells', { column: 'age', cells: [{ id: 'P1', from: '80+', to: '80' }] })]);
  assert.equal(out.get('p').rows[0][1], '80');
  assert.deepEqual(log[0].ids, ['P1']);
  assert.equal(log[0].cellsChanged, 1);
});

test('stale replace-cells throws naming the row ID', () => {
  assert.throws(() => run([T('replace-cells', { column: 'age', cells: [{ id: 'P2', from: '99', to: '1' }] })]), /P2/);
  assert.throws(() => run([T('replace-cells', { column: 'age', cells: [{ id: 'P9', from: '1', to: '2' }] })]), /P9/);
});

test('parse-dates DD/MM/YYYY', () => {
  const t = new Map([['p', { headers: ['id', 'd'], rows: [['A', '03/04/2023'], ['B', '']] }]]);
  const { tables: out, log } = run([T('parse-dates', { column: 'd', format: 'DD/MM/YYYY' })], t);
  assert.deepEqual(out.get('p').rows.map((r) => r[1]), ['2023-04-03', '']);
  assert.equal(log[0].cellsChanged, 1);
});

test('parse-dates single-digit tokens and bad rows', () => {
  const t = new Map([['p', { headers: ['id', 'd'], rows: [['A', '3.4.2023'], ['B', '12.11.2023']] }]]);
  const { tables: out } = run([T('parse-dates', { column: 'd', format: 'D.M.YYYY' })], t);
  assert.deepEqual(out.get('p').rows.map((r) => r[1]), ['2023-04-03', '2023-11-12']);
  const bad = new Map([['p', { headers: ['id', 'd'], rows: [['A', '31/02/2023'], ['B', '1/2/2023'], ['C', '01/02/2023']] }]]);
  assert.throws(() => run([T('parse-dates', { column: 'd', format: 'DD/MM/YYYY' })], bad), (e) => /A/.test(e.message) && /B/.test(e.message) && !/\bC\b/.test(e.message));
});

test('derive-column then replace-cells', () => {
  const { tables: out } = run([
    T('derive-column', { column: 'age_80plus', from: 'age', map: { '80+': 'TRUE' }, default: 'FALSE' }),
    T('replace-cells', { column: 'age', cells: [{ id: 'P1', from: '80+', to: '80' }] }),
  ]);
  assert.deepEqual(out.get('p').headers, ['id', 'age', 'note', 'age_80plus']);
  assert.deepEqual(out.get('p').rows.map((r) => [r[1], r[3]]), [['80', 'TRUE'], ['5', 'FALSE'], ['', 'FALSE']]);
  assert.throws(() => run([T('derive-column', { column: 'age', from: 'age', map: {}, default: '' })]), /age/);
});

test('ID column resolved across a later rename', () => {
  const t = new Map([['p', { headers: ['pid', 'age'], rows: [['P1', '80+']] }]]);
  const { tables: out } = run([
    T('replace-cells', { column: 'age', cells: [{ id: 'P1', from: '80+', to: '80' }] }),
    T('rename-column', { from: 'pid', to: 'id' }),
  ], t);
  assert.equal(out.get('p').rows[0][1], '80');
  assert.deepEqual(out.get('p').headers, ['id', 'age']);
});

// Runs applyTransforms in a child process with a timeout, so a looping ID lookup fails instead of hanging.
function runBounded(headers, transforms, idColumn) {
  const mod = new URL('../scripts/lib/tabular/transforms.js', import.meta.url).href;
  const code = `
    const { applyTransforms } = await import(${JSON.stringify(mod)});
    const t = new Map([['p', { headers: ${JSON.stringify(headers)}, rows: [${JSON.stringify(headers.map((h) => h + '1'))}] }]]);
    try {
      const { log } = applyTransforms(t, { entities: [{ name: 'p', idColumn: ${JSON.stringify(idColumn)} }], transforms: ${JSON.stringify(transforms)} });
      console.log(JSON.stringify({ ok: log }));
    } catch (e) { console.log(JSON.stringify({ error: e.message })); }`;
  const r = spawnSync(process.execPath, ['--input-type=module', '-e', code], { encoding: 'utf8', timeout: 5000 });
  assert.equal(r.signal, null, 'applyTransforms did not finish within 5 s (ID lookup loop?)');
  return JSON.parse(r.stdout);
}

test('missing ID column with a later rename cycle: no hang, ID column not found', () => {
  const r = runBounded(['age'], [
    T('replace-cells', { column: 'age', cells: [{ id: 'P1', from: 'age1', to: '80' }] }),
    T('rename-column', { from: 'x', to: 'pid' }),
    T('rename-column', { from: 'pid', to: 'x' }),
  ], 'pid');
  assert.match(r.error, /ID column "pid" not found/);
});

test('missing ID column with a later no-op rename: no hang', () => {
  const r = runBounded(['age'], [
    T('replace-cells', { column: 'age', cells: [{ id: 'P1', from: 'age1', to: '80' }] }),
    T('rename-column', { from: 'pid', to: 'pid' }),
  ], 'pid');
  assert.match(r.error, /ID column "pid" not found/);
  // trim looks the ID column up too; it finishes, then the no-op rename itself fails
  const t = runBounded([' age'], [T('trim'), T('rename-column', { from: 'pid', to: 'pid' })], 'pid');
  assert.match(t.error, /transforms\[1\] \(rename-column\): column "pid" not found/);
});

test('inputs are not mutated', () => {
  const t = tables();
  const before = JSON.stringify([...t]);
  run([T('trim'), T('rename-column', { from: 'age', to: 'y' }), T('drop-column', { column: 'note' })], t);
  assert.equal(JSON.stringify([...t]), before);
});

test('user value changes log the IDs of the rows that changed; auto ones log only counts', () => {
  const map = { column: 'note', map: { NA: '' } };
  const user = run([T('map-values', map)]).log[0];
  assert.deepEqual(user.ids, ['P3']);
  assert.equal(user.cellsChanged, 1);
  const auto = run([T('map-values', { ...map, approval: 'auto' })]).log[0];
  assert.equal(auto.ids, undefined);
  assert.equal(auto.cellsChanged, 1);
});

test('each value-changing op logs changed row IDs once per row when approved by the user', () => {
  assert.deepEqual(run([T('trim')]).log[0].ids, ['P1', 'P2']);
  assert.deepEqual(run([T('blank-placeholders', { values: ['NA'] })]).log[0].ids, ['P3']);
  const dates = new Map([['p', { headers: ['id', 'd'], rows: [['A', '2023-4-3'], ['B', ''], ['C', '2023-01-02']] }]]);
  assert.deepEqual(run([T('parse-dates', { column: 'd', format: 'YYYY-M-D' })], dates).log[0].ids, ['A']);
  const cells = [{ id: 'P1', from: '80+', to: '80' }, { id: 'P2', from: '5', to: '5' }];
  assert.deepEqual(run([T('replace-cells', { column: 'age', cells })]).log[0].ids, ['P1']);
});
