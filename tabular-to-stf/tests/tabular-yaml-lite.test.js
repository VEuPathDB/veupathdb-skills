import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { parseYaml, YamlLiteError } from '../scripts/lib/yaml-lite.js';
import { yamlScalar } from '../scripts/lib/stf-common.js';

test('parses the sample-annotations-to-stf golden entity YAML', () => {
  const doc = parseYaml(readFileSync(new URL('./fixtures/stf/entity-sample.yaml', import.meta.url), 'utf8'));
  assert.equal(doc.name, 'sample');
  assert.equal(doc.display_name_plural, 'Samples');
  assert.deepEqual(doc.id_columns, [{ id_column: 'sample.ID', entity_name: 'sample', provider_label: ['sample ID'] }]);
  assert.equal(doc.variables.length, 3);
  assert.equal(doc.variables[0].variable, 'SRA.ID.s.');
  assert.equal(doc.variables[0].is_multi_valued, 'yes'); // yes stays a string
  assert.equal(doc.variables[0].multi_value_delimiter, ',');
  assert.equal(doc.variables[2].definition, 'Growth condition before RNA extraction');
  assert.deepEqual(doc.categories, []);
  assert.deepEqual(doc.collections, []);
});

// Examples copied from study-wrangler v1.0.53 STF_documentation
test('parses STF docs: household entity and observation entity', () => {
  const hh = parseYaml(`name: household
display_name: Household
display_name_plural: Households

id_columns:
  - id_column: Household.Id
    entity_name: household

variables:
  - variable: Number.of.animals
    display_name: Number of animals
    data_type: integer
    data_shape: continuous

  - variable: Enrollment.date
    display_name: Enrollment date
    data_type: date
    data_shape: continuous
`);
  assert.equal(hh.variables[1].variable, 'Enrollment.date');
  assert.deepEqual(hh.id_columns, [{ id_column: 'Household.Id', entity_name: 'household' }]);

  const obs = parseYaml(`name: observation
display_name: observation
display_name_plural: observations

id_columns:
  - id_column: Household.Id
    entity_name: household
    entity_level: -2
  - id_column: Participant.Id
    entity_name: participant
    entity_level: -1
  - id_column: Part..Obs..Id
    entity_name: observation

variables:
  - variable: Observation.date
    provider_label:
      - Observation date
    data_type: date
    data_shape: continuous
# more variables not shown
`);
  assert.equal(obs.id_columns[0].entity_level, -2);
  assert.deepEqual(obs.variables[0].provider_label, ['Observation date']);
});

test('parses STF docs: study.yaml and categories/collections', () => {
  assert.deepEqual(parseYaml(`name: My Awesome Study
entities:
  - household
  - participant
  - observation
`), { name: 'My Awesome Study', entities: ['household', 'participant', 'observation'] });

  const c = parseYaml(`categories:
  - category: integer.measures
    display_name: Anthropometric measurements

collections:
  - category: integer.measures
    display_name: Anthropometric measurements
    member: measurement
    member_plural: measurements
    is_proportion: false
    is_compositional: false
    normalization_method: none
`);
  assert.equal(c.categories[0].category, 'integer.measures');
  assert.equal(c.collections[0].is_proportion, false);
  assert.equal(c.collections[0].normalization_method, 'none');
});

test('parses STF docs: site entity with stable_id and display_type', () => {
  const s = parseYaml(`name: site
display_name: Site
display_name_plural: Sites

id_columns:
  - id_column: Site.Id
    entity_name: site

variables:
  - variable: Latitude
    display_name: Latitude
    stable_id: OBI_0001620
    data_type: number
    data_shape: continuous
    display_type: latitude
`);
  assert.equal(s.variables[0].stable_id, 'OBI_0001620');
});

test('parses STF docs: participant entity with categories, ordinal levels, hidden, multi-valued', () => {
  const p = parseYaml(`name: participant
display_name: Participant
display_name_plural: Participants
description: People enrolled in the study, one row per person.

id_columns:
  - id_column: Household.Id
    entity_name: household
    entity_level: -1
  - id_column: Participant.Id
    entity_name: participant

variables:
  - variable: Name
    display_name: Full name
    data_type: string
    data_shape: categorical
    hidden:
      - everywhere

  - variable: Hemoglobin
    display_name: Hemoglobin
    data_type: number
    data_shape: continuous
    unit: g/dL
    display_range_min: '0'
    display_range_max: '20'
    bin_width_override: '0.5'

  - variable: Education
    display_name: Highest education level
    data_type: string
    data_shape: ordinal
    ordinal_levels:
      - none
      - primary
      - secondary
      - tertiary
    parent_category: demographics

  - variable: Symptoms
    display_name: Symptoms reported
    data_type: string
    data_shape: categorical
    is_multi_valued: true
    multi_value_delimiter: ';'

categories:
  - category: demographics
    display_name: Demographics
    display_order: 1

  - category: anthropometry
    display_name: Anthropometry
    definition: Body measurements.
    parent_category: clinical
    display_order: 1
`);
  assert.equal(p.description, 'People enrolled in the study, one row per person.');
  assert.deepEqual(p.variables[0].hidden, ['everywhere']);
  assert.equal(p.variables[1].display_range_max, '20'); // quoted stays a string
  assert.equal(p.variables[1].unit, 'g/dL');
  assert.deepEqual(p.variables[2].ordinal_levels, ['none', 'primary', 'secondary', 'tertiary']);
  assert.equal(p.variables[3].is_multi_valued, true);
  assert.equal(p.variables[3].multi_value_delimiter, ';');
  assert.equal(p.categories[0].display_order, 1);
  assert.equal(p.categories[1].parent_category, 'clinical');
});

test('scalar resolution', () => {
  const d = parseYaml(`a: 12
b: -3
c: 1.5
d: True
e: FALSE
f: null
g: ~
h:
i: yes
j: no
k: on
l: 007x
m: '12'
n: "true"
`);
  assert.deepEqual(d, { a: 12, b: -3, c: 1.5, d: true, e: false, f: null, g: null, h: null, i: 'yes', j: 'no', k: 'on', l: '007x', m: '12', n: 'true' });
});

test('quoting and escapes', () => {
  const d = parseYaml(`a: 'it''s'
b: "say \\"hi\\"\\\\ \\n\\tend"
c: "a: b"
"quoted key": v
`);
  assert.equal(d.a, "it's");
  assert.equal(d.b, 'say "hi"\\ \n\tend');
  assert.equal(d.c, 'a: b');
  assert.equal(d['quoted key'], 'v');
});

test('flow sequences and empty flow mapping', () => {
  const d = parseYaml(`a: []
b: [x, 'b c', "d, e", 3]
c: {}
d: [ ]
`);
  assert.deepEqual(d, { a: [], b: ['x', 'b c', 'd, e', 3], c: {}, d: [] });
});

test('block scalars', () => {
  const d = parseYaml(`lit: |
  line one
  line two

keep: |-
  no newline
fold: >
  folded
  text

  para two
foldstrip: >-
  a
  b
after: x
`);
  assert.equal(d.lit, 'line one\nline two\n');
  assert.equal(d.keep, 'no newline');
  assert.equal(d.fold, 'folded text\npara two\n');
  assert.equal(d.foldstrip, 'a b');
  assert.equal(d.after, 'x');
});

test('block scalar inside a sequence of mappings keeps # as text', () => {
  const d = parseYaml(`variables:
  - variable: a
    definition: |
      # not a comment
      second
  - variable: b
`);
  assert.equal(d.variables[0].definition, '# not a comment\nsecond\n');
  assert.equal(d.variables[1].variable, 'b');
});

test('comments: full-line and trailing', () => {
  const d = parseYaml(`# header
a: 1 # trailing
b: 'x # not a comment' # but this is
c: a#b
list:
  # inside
  - x # c
  - y
`);
  assert.deepEqual(d, { a: 1, b: 'x # not a comment', c: 'a#b', list: ['x', 'y'] });
});

test('sequence at the same indent as its key, nested sequences, CRLF, BOM, leading ---', () => {
  assert.deepEqual(parseYaml('k:\n- a\n- b: 1\n  c: 2\nz: 3\n'), { k: ['a', { b: 1, c: 2 }], z: 3 });
  assert.deepEqual(parseYaml('- - a\n  - b\n- c\n'), [['a', 'b'], 'c']);
  assert.deepEqual(parseYaml('\uFEFFa: 1\r\nb: x\r\n'), { a: 1, b: 'x' });
  assert.deepEqual(parseYaml('---\na: 1\n'), { a: 1 });
  assert.equal(parseYaml(''), null);
});

test('unsupported constructs throw YamlLiteError with the line', () => {
  const cases = [
    ['a: 1\nb: &x 2\n', 2],
    ['a: 1\nb: *x\n', 2],
    ['a: 1\nb: !!str 2\n', 2],
    ['a: 1\n---\nb: 2\n', 2],
    ['a: 1\nb: {x: 1}\n', 2],
    ['a: 1\nb: [a, [b]]\n', 2],
    ['a: 1\nb: [a,\n  b]\n', 2],
    ['a: 1\nb: "unterminated\n', 2],
    ['a: 1\nb: "bad \\q"\n', 2],
    ['a: 1\n\tb: 2\n', 2],
    ['a: 1\n  b: 2\n', 2],
    ['- &x a\n', 1],
  ];
  for (const [text, line] of cases) {
    assert.throws(() => parseYaml(text), e => e instanceof YamlLiteError && e.line === line, JSON.stringify(text));
  }
});

test('round trip: yamlScalar output parses back to the same string', () => {
  const strings = ['yes', 'no', 'on', 'off', 'null', 'Null', '~', 'true', 'False', '1.0', '007', '12', '-3', '.5',
    'a: b', 'a:', '#x', '-x', '- x', '- ', 'x #y', "it's", '', ' lead', 'trail ', '[a]', '{a}', '&a', '*a', '!t',
    '%x', '@x', '`x', '|', '>', '?', ',x', "'q'", '"q"', 'line1\nline2', 'a\tb', 'say "hi"\nnext', 'cr\r\nlf\\', 'plain', 'a,b', 'p#q', 'http://x/y',
    '0x1F', '0o17', '0b101', '.inf', '-.Inf', '.NaN', '1.', '1e3', '1_000', '1:30'];
  for (const s of strings) {
    const out = parseYaml(`k: ${yamlScalar(s)}\n`);
    assert.strictEqual(out.k, s, `value ${JSON.stringify(s)} via ${JSON.stringify(yamlScalar(s))}`);
  }
});
