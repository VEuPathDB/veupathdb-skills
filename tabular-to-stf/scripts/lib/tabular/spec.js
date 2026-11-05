/**
 * Curation spec validator. Checks the JSON spec the curator writes; never
 * reads files. Returns every error found, each naming its location.
 */

import { isValidColumnName } from '../stf-common.js';
import { UNAMBIGUOUS_PLACEHOLDERS } from './profile.js';
import { STF_CONSTANTS } from './stf-constants.js';

const APPROVALS = ['auto', 'user', 'proposed', 'rejected'];
const ENTITY_NAME = /^[a-z][a-z0-9_]*$/;

const isObj = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);
const isStr = (v) => typeof v === 'string' && v !== '';
const isStrArray = (v) => Array.isArray(v) && v.every((x) => typeof x === 'string');
// A path inside inputDir: relative, with no `..` segment.
const isInsidePath = (v) => isStr(v) && !/^([\\/]|[A-Za-z]:)/.test(v) && !v.split(/[\\/]/).includes('..');
const NOTE_LISTS = ['flagged', 'decisions', 'pii', 'validation'];

// Required fields per op; `auto` allowed unconditionally, never, or by a predicate on the transform.
const OPS = {
  'trim': { auto: () => true },
  'blank-placeholders': {
    auto: (t) => Array.isArray(t.values) && t.values.every((v) => UNAMBIGUOUS_PLACEHOLDERS.includes(v)),
  },
  'map-values': { auto: () => true },
  'rename-column': { auto: () => true },
  'replace-cells': { auto: () => false },
  'parse-dates': { auto: () => false },
  'derive-column': { auto: () => false },
  'drop-column': { auto: () => false },
};

function checkTransform(t, i, entityNames, errors) {
  const at = `transforms[${i}]`;
  if (!isObj(t)) { errors.push(`${at}: must be an object`); return; }
  const op = OPS[t.op];
  if (!op) errors.push(`${at}.op: unknown op ${JSON.stringify(t.op)}`);
  if (!entityNames.has(t.entity)) errors.push(`${at}.entity: unknown entity ${JSON.stringify(t.entity)}`);
  if (!isStr(t.reason)) errors.push(`${at}.reason: required`);
  if (!APPROVALS.includes(t.approval)) {
    errors.push(`${at}.approval: must be one of ${APPROVALS.join(', ')}`);
  } else {
    if (t.approval === 'rejected' && !isStr(t.instead)) errors.push(`${at}.instead: required when approval is "rejected"`);
    if (t.approval === 'auto' && op && !op.auto(t)) {
      errors.push(`${at}.approval: "auto" is not allowed for ${t.op}${t.op === 'blank-placeholders' ? ' unless values are all unambiguous placeholders' : ''}; use "user"`);
    }
  }
  if (!op) return;
  const need = (field, ok, what) => { if (!ok(t[field])) errors.push(`${at}.${field}: ${what}`); };
  const needStr = (f) => need(f, isStr, 'required string');
  const optCols = () => { if (t.columns !== undefined && !(Array.isArray(t.columns) && t.columns.every(isStr))) errors.push(`${at}.columns: must be an array of strings`); };
  switch (t.op) {
    case 'trim': optCols(); break;
    case 'blank-placeholders':
      optCols();
      need('values', (v) => Array.isArray(v) && v.length > 0 && v.every((x) => typeof x === 'string'), 'required non-empty array of strings');
      break;
    case 'map-values':
      needStr('column');
      need('map', (m) => isObj(m) && Object.values(m).every((x) => typeof x === 'string'), 'required object of strings');
      break;
    case 'rename-column':
      needStr('from'); needStr('to');
      if (isStr(t.from) && t.from === t.to) errors.push(`${at}.to: same as from (${JSON.stringify(t.from)}); a rename must change the name`);
      break;
    case 'replace-cells':
      needStr('column');
      need('cells', (c) => Array.isArray(c) && c.every((x) => isObj(x) && isStr(x.id) && typeof x.from === 'string' && typeof x.to === 'string'),
        'required array of { id, from, to } strings');
      break;
    case 'parse-dates': needStr('column'); needStr('format'); break;
    case 'derive-column':
      needStr('column'); needStr('from');
      need('map', (m) => isObj(m) && Object.values(m).every((x) => typeof x === 'string'), 'required object of strings');
      need('default', (d) => typeof d === 'string', 'required string');
      break;
    case 'drop-column': needStr('column'); break;
  }
}

function hasCycle(parentOf, start) {
  const seen = new Set();
  for (let n = start; n !== undefined; n = parentOf.get(n)) {
    if (seen.has(n)) return true;
    seen.add(n);
  }
  return false;
}

function checkEntity(e, i, entityNames, errors) {
  const at = `entities[${i}]`;
  if (!isObj(e)) { errors.push(`${at}: must be an object`); return; }
  for (const f of ['displayName', 'displayNamePlural', 'file', 'idColumn']) if (!isStr(e[f])) errors.push(`${at}.${f}: required string`);
  if (isStr(e.file) && !isInsidePath(e.file)) errors.push(`${at}.file: must be relative to inputDir, with no ".." segment (got ${JSON.stringify(e.file)})`);
  if (e.idName !== undefined && !(typeof e.idName === 'string' && isValidColumnName(e.idName))) errors.push(`${at}.idName: invalid column name ${JSON.stringify(e.idName)}`);
  if (e.parent !== undefined) {
    if (!entityNames.has(e.parent)) errors.push(`${at}.parent: unknown entity ${JSON.stringify(e.parent)}`);
    if (!isStr(e.parentColumn)) errors.push(`${at}.parentColumn: required when parent is set`);
  }
  if (e.geo !== undefined && !(isObj(e.geo) && isStr(e.geo.latitude) && isStr(e.geo.longitude))) errors.push(`${at}.geo: needs latitude and longitude column names`);

  const cats = e.categories === undefined ? [] : e.categories;
  if (!Array.isArray(cats)) { errors.push(`${at}.categories: must be an array`); return; }
  const catNames = new Set();
  const catParent = new Map();
  cats.forEach((c, j) => {
    const cat = `${at}.categories[${j}]`;
    if (!isObj(c) || !isStr(c.category)) { errors.push(`${cat}.category: required string`); return; }
    if (catNames.has(c.category)) errors.push(`${cat}.category: duplicate ${JSON.stringify(c.category)}`);
    catNames.add(c.category);
    if (!isStr(c.displayName)) errors.push(`${cat}.displayName: required string`);
    if (c.definition !== undefined && typeof c.definition !== 'string') errors.push(`${cat}.definition: must be a string`);
    if (c.parentCategory !== undefined) catParent.set(c.category, c.parentCategory);
  });
  cats.forEach((c, j) => {
    if (!isObj(c) || c.parentCategory === undefined) return;
    if (!catNames.has(c.parentCategory)) errors.push(`${at}.categories[${j}].parentCategory: unknown category ${JSON.stringify(c.parentCategory)}`);
    else if (hasCycle(catParent, c.category)) errors.push(`${at}.categories[${j}].parentCategory: category cycle through ${JSON.stringify(c.category)}`);
  });

  if (!Array.isArray(e.variables)) { errors.push(`${at}.variables: must be an array`); return; }
  e.variables.forEach((v, j) => {
    const vt = `${at}.variables[${j}]`;
    if (!isObj(v)) { errors.push(`${vt}: must be an object`); return; }
    if (!isStr(v.column)) errors.push(`${vt}.column: required string`);
    if (v.name !== undefined && !(typeof v.name === 'string' && isValidColumnName(v.name))) errors.push(`${vt}.name: invalid column name ${JSON.stringify(v.name)}`);
    if (v.dataType !== undefined && !STF_CONSTANTS.DATA_TYPES.includes(v.dataType)) errors.push(`${vt}.dataType: must be one of ${STF_CONSTANTS.DATA_TYPES.join(', ')}`);
    if (v.dataShape !== undefined && !STF_CONSTANTS.DATA_SHAPES.includes(v.dataShape)) errors.push(`${vt}.dataShape: must be one of ${STF_CONSTANTS.DATA_SHAPES.join(', ')}`);
    if (v.displayType !== undefined && !STF_CONSTANTS.DISPLAY_TYPES.includes(v.displayType)) errors.push(`${vt}.displayType: must be one of ${STF_CONSTANTS.DISPLAY_TYPES.join(', ')}`);
    if (v.parentCategory !== undefined && !catNames.has(v.parentCategory)) errors.push(`${vt}.parentCategory: unknown category ${JSON.stringify(v.parentCategory)}`);
    for (const f of ['unit', 'definition', 'displayName', 'providerLabel']) {
      if (v[f] !== undefined && typeof v[f] !== 'string') errors.push(`${vt}.${f}: must be a string`);
    }
    for (const f of ['ordinalLevels', 'vocabularyOrder']) {
      if (v[f] !== undefined && !isStrArray(v[f])) errors.push(`${vt}.${f}: must be an array of strings`);
    }
  });
}

export function validateSpec(spec) {
  const errors = [];
  if (!isObj(spec)) return ['spec: must be an object'];
  if (spec.specVersion !== 1) errors.push('specVersion: must be 1');
  if (!isObj(spec.study) || !isStr(spec.study.name)) errors.push('study.name: required string');
  if (!isStr(spec.inputDir)) errors.push('inputDir: required string');
  if (spec.extraFiles !== undefined && !(Array.isArray(spec.extraFiles) && spec.extraFiles.every(isStr))) errors.push('extraFiles: must be an array of strings');
  else (spec.extraFiles || []).forEach((f, i) => {
    if (!isInsidePath(f)) errors.push(`extraFiles[${i}]: must be relative to inputDir, with no ".." segment (got ${JSON.stringify(f)})`);
  });
  if (spec.notes !== undefined) {
    if (!isObj(spec.notes)) errors.push('notes: must be an object');
    else for (const k of NOTE_LISTS) if (spec.notes[k] !== undefined && !isStrArray(spec.notes[k])) errors.push(`notes.${k}: must be an array of strings`);
  }
  if (!Array.isArray(spec.entities) || spec.entities.length === 0) {
    errors.push('entities: required non-empty array');
    return errors;
  }

  const entityNames = new Set();
  spec.entities.forEach((e, i) => {
    const name = isObj(e) ? e.name : undefined;
    if (typeof name !== 'string' || !ENTITY_NAME.test(name)) errors.push(`entities[${i}].name: must match ${ENTITY_NAME}`);
    else if (entityNames.has(name)) errors.push(`entities[${i}].name: duplicate entity ${JSON.stringify(name)}`);
    else entityNames.add(name);
  });
  spec.entities.forEach((e, i) => checkEntity(e, i, entityNames, errors));

  const roots = spec.entities.filter((e) => isObj(e) && e.parent === undefined);
  if (roots.length !== 1) errors.push(`entities: need exactly one root (entity without parent), found ${roots.length}`);
  const parentOf = new Map(spec.entities.filter((e) => isObj(e) && e.parent !== undefined).map((e) => [e.name, e.parent]));
  spec.entities.forEach((e, i) => {
    if (isObj(e) && e.parent !== undefined && hasCycle(parentOf, e.name)) errors.push(`entities[${i}].parent: parent cycle through ${JSON.stringify(e.name)}`);
  });

  const transforms = spec.transforms === undefined ? [] : spec.transforms;
  if (!Array.isArray(transforms)) errors.push('transforms: must be an array');
  else transforms.forEach((t, i) => checkTransform(t, i, entityNames, errors));
  return errors;
}
