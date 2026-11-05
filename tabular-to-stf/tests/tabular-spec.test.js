import { test } from 'node:test';
import assert from 'node:assert/strict';
import { validateSpec } from '../scripts/lib/tabular/spec.js';
import { STF_CONSTANTS } from '../scripts/lib/tabular/stf-constants.js';

function minimal() {
  return {
    specVersion: 1,
    study: { name: 'Demo' },
    inputDir: 'raw-data',
    entities: [
      {
        name: 'household', displayName: 'Household', displayNamePlural: 'Households',
        file: 'household.csv', idColumn: 'household_id',
        variables: [{ column: 'size', displayName: 'Size' }],
      },
      {
        name: 'participant', displayName: 'Participant', displayNamePlural: 'Participants',
        file: 'participants.csv', idColumn: 'participant_id',
        parent: 'household', parentColumn: 'household_id',
        variables: [{ column: 'age', name: 'age_years', displayName: 'Age', dataType: 'integer', dataShape: 'continuous' }],
        categories: [{ category: 'demo', displayName: 'Demo' }],
      },
    ],
    transforms: [],
  };
}

test('constants are frozen with the expected values', () => {
  assert.deepEqual(STF_CONSTANTS.DATA_TYPES, ['string', 'number', 'integer', 'date', 'longitude']);
  assert.deepEqual(STF_CONSTANTS.HIDDEN, ['download', 'variableTree', 'map', 'everywhere']);
  assert.ok(Object.isFrozen(STF_CONSTANTS.DATA_SHAPES));
});

test('valid minimal spec gives no errors', () => {
  assert.deepEqual(validateSpec(minimal()), []);
});

test('two roots are reported', () => {
  const s = minimal();
  delete s.entities[1].parent;
  delete s.entities[1].parentColumn;
  assert.ok(validateSpec(s).some((e) => /root/.test(e)));
});

test('parent cycle is reported', () => {
  const s = minimal();
  s.entities[0].parent = 'participant';
  s.entities[0].parentColumn = 'participant_id';
  const errs = validateSpec(s);
  assert.ok(errs.some((e) => /cycle/.test(e)));
});

test('unknown parent entity is reported', () => {
  const s = minimal();
  s.entities[1].parent = 'nowhere';
  assert.ok(validateSpec(s).some((e) => /entities\[1\]\.parent/.test(e)));
});

test('unknown parentCategory is reported', () => {
  const s = minimal();
  s.entities[1].variables[0].parentCategory = 'missing';
  assert.ok(validateSpec(s).some((e) => /entities\[1\]\.variables\[0\]\.parentCategory/.test(e)));
});

test('category cycle is reported', () => {
  const s = minimal();
  s.entities[1].categories = [
    { category: 'a', displayName: 'A', parentCategory: 'b' },
    { category: 'b', displayName: 'B', parentCategory: 'a' },
  ];
  assert.ok(validateSpec(s).some((e) => /category cycle/.test(e)));
});

test('replace-cells cannot be auto', () => {
  const s = minimal();
  s.transforms = [{ op: 'replace-cells', entity: 'participant', column: 'age', cells: [], reason: 'r', approval: 'auto' }];
  assert.ok(validateSpec(s).some((e) => /transforms\[0\]\.approval/.test(e)));
});

test('blank-placeholders auto only for unambiguous values', () => {
  const s = minimal();
  s.transforms = [{ op: 'blank-placeholders', entity: 'participant', values: ['unknown'], reason: 'r', approval: 'auto' }];
  assert.ok(validateSpec(s).some((e) => /transforms\[0\]\.approval/.test(e)));
  s.transforms[0].values = ['NA'];
  assert.deepEqual(validateSpec(s), []);
  s.transforms[0].values = ['unknown'];
  s.transforms[0].approval = 'user';
  assert.deepEqual(validateSpec(s), []);
});

test('bad dataType, bad name, bad approval, missing instead, unknown entity', () => {
  const s = minimal();
  s.entities[1].variables[0].dataType = 'float';
  s.entities[1].variables[0].name = '1bad';
  s.entities[0].idName = 'bad name';
  s.transforms = [
    { op: 'trim', entity: 'ghost', reason: 'r', approval: 'auto' },
    { op: 'trim', entity: 'participant', reason: 'r', approval: 'maybe' },
    { op: 'trim', entity: 'participant', reason: 'r', approval: 'rejected' },
  ];
  const errs = validateSpec(s);
  assert.ok(errs.some((e) => /entities\[1\]\.variables\[0\]\.dataType/.test(e)));
  assert.ok(errs.some((e) => /entities\[1\]\.variables\[0\]\.name/.test(e)));
  assert.ok(errs.some((e) => /entities\[0\]\.idName/.test(e)));
  assert.ok(errs.some((e) => /transforms\[0\]\.entity/.test(e)));
  assert.ok(errs.some((e) => /transforms\[1\]\.approval/.test(e)));
  assert.ok(errs.some((e) => /transforms\[2\]\.instead/.test(e)));
});

test('non-object spec does not throw', () => {
  assert.ok(validateSpec(null).length > 0);
  assert.ok(validateSpec({}).length > 0);
});

test('rename-column with from === to is rejected', () => {
  const s = minimal();
  s.transforms = [{ op: 'rename-column', entity: 'participant', from: 'age', to: 'age', reason: 'r', approval: 'auto' }];
  assert.ok(validateSpec(s).some((e) => /transforms\[0\]\.to: same as from/.test(e)));
  s.transforms[0].to = 'age_years';
  assert.deepEqual(validateSpec(s), []);
});

test('entity file and extraFiles must stay inside inputDir', () => {
  for (const bad of ['/etc/passwd', '../x.csv', 'a/../../x.csv', 'a\\..\\x.csv', 'C:\\x.csv']) {
    const s = minimal();
    s.entities[0].file = bad;
    s.extraFiles = ['ok.md', bad];
    const errs = validateSpec(s);
    assert.ok(errs.some((e) => /^entities\[0\]\.file: must be relative to inputDir/.test(e)), `${bad}: ${errs}`);
    assert.ok(errs.some((e) => /^extraFiles\[1\]: must be relative/.test(e)), `${bad}: ${errs}`);
    assert.ok(!errs.some((e) => /extraFiles\[0\]/.test(e)));
  }
  const s = minimal();
  s.entities[0].file = 'sub/dir/household.csv';
  s.extraFiles = ['docs/dict..v2.xlsx'];
  assert.deepEqual(validateSpec(s), []);
});

test('notes lists, value lists and text fields are type-checked, with paths', () => {
  const s = minimal();
  s.notes = { flagged: ['ok'], decisions: 'one string', pii: [1], validation: ['ok'] };
  const v = s.entities[1].variables[0];
  Object.assign(v, { unit: 5, definition: ['x'], displayName: null, providerLabel: {}, ordinalLevels: ['a', 2], vocabularyOrder: 'a,b' });
  s.entities[1].categories[0].definition = 3;
  const errs = validateSpec(s);
  for (const want of ['notes.decisions: must be an array of strings', 'notes.pii: must be an array of strings',
    'entities[1].variables[0].unit: must be a string', 'entities[1].variables[0].definition: must be a string',
    'entities[1].variables[0].displayName: must be a string', 'entities[1].variables[0].providerLabel: must be a string',
    'entities[1].variables[0].ordinalLevels: must be an array of strings', 'entities[1].variables[0].vocabularyOrder: must be an array of strings',
    'entities[1].categories[0].definition: must be a string']) {
    assert.ok(errs.includes(want), `missing ${want} in ${errs.join(' | ')}`);
  }
  assert.ok(!errs.some((e) => /notes\.(flagged|validation)/.test(e)));
  assert.deepEqual(validateSpec({ ...minimal(), notes: [] }), ['notes: must be an object']);
});
