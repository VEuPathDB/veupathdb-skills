import { test } from 'node:test';
import assert from 'node:assert/strict';
import { yamlScalar, inferType, isValidColumnName, toColumnName, uniqueColumnNames } from '../scripts/lib/stf-common.js';

test('toColumnName gives snake_case names that need no quoting', () => {
  assert.equal(toColumnName('Age (years)'), 'age_years');
  assert.equal(toColumnName('1st visit'), 'x1st_visit');
  assert.equal(toColumnName('_id'), 'id');
  assert.equal(toColumnName('Hb (g/dL)'), 'hb_g_dl');
  assert.equal(toColumnName('°C'), 'c');
  assert.equal(toColumnName('%%'), 'x');
  assert.equal(toColumnName('participant_id'), 'participant_id');
});

test('uniqueColumnNames suffixes later duplicates', () => {
  assert.deepEqual(uniqueColumnNames(['a_b', 'a_b', 'c', 'a_b']), ['a_b', 'a_b_2', 'c', 'a_b_3']);
});

test('isValidColumnName', () => {
  for (const ok of ['age', 'Age_2', 'x1']) assert.ok(isValidColumnName(ok));
  for (const bad of ['1age', '_age', 'a.b', 'a b', '', 'ä']) assert.ok(!isValidColumnName(bad));
});

test('yamlScalar quotes YAML 1.1 booleans, numbers and multi-line text', () => {
  for (const s of ['on', 'OFF', 'y', 'N', 'yes', 'null', '1.0', 'a: b', '#x', '-x', '+5', '.5']) assert.match(yamlScalar(s), /^'/);
  for (const s of ['0x1F', '0X1f', '0o17', '0b101', '.inf', '-.Inf', '+.INF', '.NaN', '1.', '1e3', '1E-3', '1.5e+3', '1_000', '1:30', '-1:30:05.5'])
    assert.match(yamlScalar(s), /^'/, s);
  for (const s of ['0x', '1.2.3', '1e', 'e3', 'inf', 'NaN', '.infinity', '12:60', 'x1', '1a', 'v1.0']) assert.equal(yamlScalar(s), s, s);
  assert.equal(yamlScalar("it's"), "it's");
  assert.equal(yamlScalar('a\nb'), '"a\\nb"');
  assert.equal(yamlScalar('a\tb'), '"a\\tb"');
  assert.equal(yamlScalar('say "hi"\r\n\\'), '"say \\"hi\\"\\r\\n\\\\"');
});

test('inferType keeps leading-zero codes as strings', () => {
  assert.deepEqual(inferType(['007', '012']), { data_type: 'string', data_shape: 'categorical' });
});
