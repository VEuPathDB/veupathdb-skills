/**
 * STF directory checker. Reads study.yaml, entity-<name>.{tsv,yaml} and
 * curation-notes.md and reports every problem found; the goal is that a pass
 * means `study_from_stf(dir, validate = FALSE)` loads in study-wrangler.
 * Read-only, and it ignores subdirectories (raw-data/ included) and files
 * study.yaml does not name, as the loaders do.
 *
 * Handles the standard layout of full STF only. STF-lite and transposed entity
 * files are reported, not checked: validate those in mode 2.
 */

import { readFileSync, existsSync, statSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { parseYaml } from '../yaml-lite.js';
import { isValidColumnName } from '../stf-common.js';
import { parseDelimited } from './read-table.js';
import { STF_CONSTANTS } from './stf-constants.js';
import { STUDY_WRANGLER_VERSION } from '../tools/study-wrangler-container.js';
import { GEO, isLatitudeName, isLongitudeName, validatorSeesLatitude, validatorSeesLongitude } from './geo.js';

export { STUDY_WRANGLER_VERSION };

const MARKER = ' \\\\ Descriptors';
const MAX_PER_KIND = 5; // value errors reported per file, column and kind

const isObj = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);
const asList = (v) => (v === undefined || v === null ? [] : Array.isArray(v) ? v : [v]);
const isMissing = (v) => v === '' || v === 'NA';
const NUMBER = /^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$/;
const INTEGER = /^[+-]?\d+$/;

/** Numeric dotted-version comparison: negative, 0 or positive. */
function compareVersions(a, b) {
  const pa = a.split('.').map(Number);
  const pb = b.split('.').map(Number);
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const d = (pa[i] ?? 0) - (pb[i] ?? 0);
    if (d !== 0) return d;
  }
  return 0;
}

export function geohashWarning(version = STUDY_WRANGLER_VERSION) {
  return compareVersions(version, '1.0.53') < 0
    ? 'geohash columns present; drop them before mode 2 validation, since study-wrangler <1.0.53 would duplicate them'
    : 'geohash columns present; they will be recomputed by infer_geo_variables_for_eda()';
}

function validDate(s) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  if (!m) return false;
  const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
  return d.getUTCFullYear() === +m[1] && d.getUTCMonth() === +m[2] - 1 && d.getUTCDate() === +m[3];
}

// Why `value` is not a valid `type`, or null. `display` is the variable's display_type.
function valueProblem(value, v) {
  switch (v.data_type) {
    case 'date': return validDate(value) ? null : 'is not a valid YYYY-MM-DD date';
    case 'integer': return INTEGER.test(value) ? null : 'is not an integer';
    case 'number':
    case 'longitude':
      if (!NUMBER.test(value)) return 'is not a number';
      break;
    default: break;
  }
  const n = Number(value);
  if (v.data_type === 'longitude' && !(n >= -180 && n <= 180)) return 'is outside -180..180';
  if (v.display_type === 'latitude') {
    if (!NUMBER.test(value)) return 'is not a number';
    if (!(n >= -90 && n <= 90)) return 'is outside -90..90';
  }
  return null;
}

function loadYaml(dir, name, errors) {
  const path = join(dir, name);
  try {
    return parseYaml(readFileSync(path, 'utf8'));
  } catch (err) {
    errors.push(`${name}: cannot parse YAML: ${err.message}`);
    return null;
  }
}

/** Load study.yaml and every listed entity's TSV and YAML. Returns null if nothing can be checked. */
function loadStudy(dir, errors) {
  const files = readdirSync(dir);
  if (!existsSync(join(dir, 'study.yaml'))) {
    if (!files.some((f) => /^entity-.*\.yaml$/.test(f))) {
      errors.push('study.yaml: missing, and no entity-<name>.yaml files either; STF-lite not supported; validate in mode 2');
    } else {
      errors.push('study.yaml: missing');
    }
    return null;
  }
  const study = loadYaml(dir, 'study.yaml', errors);
  if (!study) return null;
  if (!isObj(study)) { errors.push('study.yaml: must be a mapping with name and entities'); return null; }
  if (typeof study.name !== 'string' || study.name === '') errors.push('study.yaml: name is required');
  const names = asList(study.entities);
  if (names.length === 0 || !names.every((n) => typeof n === 'string' && n !== '')) {
    errors.push('study.yaml: entities must be a non-empty list of entity names');
    return null;
  }
  if (new Set(names).size !== names.length) errors.push('study.yaml: duplicate entity in entities');

  const entities = new Map();
  for (const name of names) {
    const yamlFile = `entity-${name}.yaml`;
    const tsvFile = `entity-${name}.tsv`;
    const haveYaml = existsSync(join(dir, yamlFile));
    const haveTsv = existsSync(join(dir, tsvFile));
    if (!haveYaml) errors.push(`${yamlFile}: missing (listed in study.yaml)`);
    if (!haveTsv) errors.push(`${tsvFile}: missing (listed in study.yaml)`);
    if (!haveYaml || !haveTsv) continue;
    const meta = loadYaml(dir, yamlFile, errors);
    if (!meta) continue;
    if (!isObj(meta)) { errors.push(`${yamlFile}: must be a mapping`); continue; }
    if (meta.name !== name) errors.push(`${yamlFile}: name is ${JSON.stringify(meta.name)} but study.yaml lists ${JSON.stringify(name)}`);
    let table;
    try {
      table = parseDelimited(readFileSync(join(dir, tsvFile), 'utf8'), '\t', tsvFile);
    } catch (err) {
      errors.push(`${tsvFile}: ${err.message}`);
      continue;
    }
    entities.set(name, { name, yamlFile, tsvFile, meta, table });
  }
  return { study, entities };
}

function checkNotes(dir, warnings) {
  const path = join(dir, 'curation-notes.md');
  if (!existsSync(path)) return;
  const mentioned = new Set(readFileSync(path, 'utf8').match(/raw-data\/[^\s`'"()<>\]]+/g) || []);
  for (const m of mentioned) {
    const p = m.replace(/[.,;:]+$/, '');
    if (!existsSync(join(dir, p))) warnings.push(`curation-notes.md: mentions ${p}, which does not exist`);
  }
}

/** Entity tree from the entity_level -1 links. Returns { parentOf, roots }; reports problems. */
function checkTree(entities, errors) {
  const parentOf = new Map();
  const roots = [];
  for (const e of entities.values()) {
    const ids = asList(e.meta.id_columns).filter(isObj);
    e.ids = ids;
    const own = ids.filter((c) => c.entity_name === e.name);
    const ancestors = ids.filter((c) => c.entity_name !== e.name);
    e.own = own.length === 1 ? own[0] : null;
    if (own.length !== 1) errors.push(`${e.yamlFile}: need exactly one id_column with entity_name ${e.name} (its own ID); found ${own.length}`);
    if (own.some((c) => c.entity_level !== undefined && c.entity_level !== 0)) errors.push(`${e.yamlFile}: the own ID column must have entity_level 0`);
    e.ancestors = ancestors;
    const levels = new Map();
    for (const c of ancestors) {
      const lvl = c.entity_level;
      if (!Number.isInteger(lvl) || lvl >= 0) { errors.push(`${e.yamlFile}: id_column ${c.id_column} has entity_level ${JSON.stringify(lvl)}; ancestors need a negative integer`); continue; }
      if (levels.has(lvl)) errors.push(`${e.yamlFile}: two id_columns have entity_level ${lvl}`);
      levels.set(lvl, c);
    }
    const parentCol = levels.get(-1);
    if (parentCol) {
      if (!entities.has(parentCol.entity_name)) errors.push(`${e.yamlFile}: id_column ${parentCol.id_column} names entity ${JSON.stringify(parentCol.entity_name)}, which study.yaml does not list`);
      else parentOf.set(e.name, parentCol.entity_name);
    } else {
      roots.push(e.name);
      if (ancestors.length) {
        const odd = ancestors.map((c) => `${c.id_column} has entity_level ${c.entity_level}`).join('; ');
        errors.push(`${e.yamlFile}: no id_column with entity_level -1 (the immediate parent); ${odd}`);
      }
    }
  }
  if (roots.length > 1) errors.push(`study.yaml: more than one root entity (no entity_level -1 column): ${roots.join(', ')}`);
  if (roots.length === 0 && entities.size > 0) errors.push('study.yaml: no root entity (every entity has a parent)');
  let cyclic = false;
  for (const name of parentOf.keys()) {
    const seen = new Set([name]);
    for (let n = parentOf.get(name); n !== undefined; n = parentOf.get(n)) {
      if (seen.has(n)) { cyclic = true; errors.push(`study.yaml: entity cycle through ${name}`); break; }
      seen.add(n);
    }
  }
  if (cyclic) return null;
  // Each ancestor id column must sit at its distance in the tree
  for (const e of entities.values()) {
    const chain = [];
    for (let n = parentOf.get(e.name); n !== undefined; n = parentOf.get(n)) chain.push(n);
    for (const c of e.ancestors) {
      if (!entities.has(c.entity_name)) {
        if (c.entity_level !== -1) errors.push(`${e.yamlFile}: id_column ${c.id_column} names entity ${JSON.stringify(c.entity_name)}, which study.yaml does not list`);
        continue;
      }
      const ownName = entities.get(c.entity_name).own?.id_column;
      if (ownName !== undefined && c.id_column !== ownName) errors.push(`${e.yamlFile}: id_column ${c.id_column} refers to ${c.entity_name}, whose own ID column is ${ownName}; study-wrangler joins on the name, so it must be ${ownName}`);
      const at = chain.indexOf(c.entity_name);
      if (at < 0) errors.push(`${e.yamlFile}: id_column ${c.id_column}: ${c.entity_name} is not an ancestor of ${e.name}`);
      else if (c.entity_level !== -(at + 1)) errors.push(`${e.yamlFile}: id_column ${c.id_column} has entity_level ${c.entity_level} but ${c.entity_name} is ${at + 1} level(s) up, so it must be ${-(at + 1)}`);
    }
  }
  return parentOf;
}

/** Reports at most MAX_PER_KIND errors per key, then one line saying how many more. */
function limiter(errors) {
  const counts = new Map();
  const report = (key, msg) => {
    const n = (counts.get(key) || 0) + 1;
    counts.set(key, n);
    if (n <= MAX_PER_KIND) errors.push(msg);
  };
  const flush = () => {
    for (const [key, n] of counts) if (n > MAX_PER_KIND) errors.push(`${key}: ${n - MAX_PER_KIND} more like this not shown`);
  };
  return { report, flush };
}

function checkVariableMeta(e, errors) {
  const { yamlFile, meta } = e;
  const variables = asList(meta.variables);
  const categories = asList(meta.categories);
  const names = new Map();
  const note = (kind, n) => {
    if (typeof n !== 'string' || n === '') { errors.push(`${yamlFile}: a ${kind} has no name`); return; }
    if (names.has(n)) errors.push(`${yamlFile}: duplicate name ${n} (${names.get(n)} and ${kind})`);
    else names.set(n, kind);
  };
  for (const v of variables) {
    if (!isObj(v)) { errors.push(`${yamlFile}: variables entries must be mappings`); continue; }
    note('variable', v.variable);
    const at = `${yamlFile}: variable ${v.variable}`;
    if (v.data_type !== undefined && !STF_CONSTANTS.DATA_TYPES.includes(v.data_type)) errors.push(`${at}: data_type ${JSON.stringify(v.data_type)} is not one of ${STF_CONSTANTS.DATA_TYPES.join(', ')}`);
    if (v.data_shape !== undefined && !STF_CONSTANTS.DATA_SHAPES.includes(v.data_shape)) errors.push(`${at}: data_shape ${JSON.stringify(v.data_shape)} is not one of ${STF_CONSTANTS.DATA_SHAPES.join(', ')}`);
    if (v.display_type !== undefined && !STF_CONSTANTS.DISPLAY_TYPES.includes(v.display_type)) errors.push(`${at}: display_type ${JSON.stringify(v.display_type)} is not one of ${STF_CONSTANTS.DISPLAY_TYPES.join(', ')}`);
    for (const h of asList(v.hidden)) {
      if (!STF_CONSTANTS.HIDDEN.includes(h)) errors.push(`${at}: hidden ${JSON.stringify(h)} is not one of ${STF_CONSTANTS.HIDDEN.join(', ')}`);
    }
    if (v.data_shape === 'ordinal' && asList(v.ordinal_levels).length === 0) errors.push(`${at}: data_shape ordinal requires ordinal_levels`);
  }
  const catNames = new Set();
  for (const c of categories) {
    if (!isObj(c)) { errors.push(`${yamlFile}: categories entries must be mappings`); continue; }
    note('category', c.category);
    catNames.add(c.category);
  }
  for (const v of variables) {
    if (isObj(v) && v.parent_category !== undefined && !catNames.has(v.parent_category)) errors.push(`${yamlFile}: variable ${v.variable}: parent_category ${JSON.stringify(v.parent_category)} names no category in ${e.name}`);
  }
  const parentOf = new Map();
  for (const c of categories) {
    if (!isObj(c) || c.parent_category === undefined) continue;
    if (!catNames.has(c.parent_category)) errors.push(`${yamlFile}: category ${c.category}: parent_category ${JSON.stringify(c.parent_category)} names no category in ${e.name}`);
    else parentOf.set(c.category, c.parent_category);
  }
  const cycled = new Set();
  for (const start of parentOf.keys()) {
    const seen = new Set([start]);
    for (let n = parentOf.get(start); n !== undefined; n = parentOf.get(n)) {
      if (seen.has(n)) { if (!cycled.has(n)) errors.push(`${yamlFile}: category cycle through ${n}`); for (const s of seen) cycled.add(s); break; }
      seen.add(n);
    }
  }
}

function checkGeoMeta(e, errors, warnings) {
  const { yamlFile } = e;
  const variables = asList(e.meta.variables).filter((v) => isObj(v) && typeof v.variable === 'string');
  const seenBy = (v, fn) => [v.variable, ...asList(v.provider_label)].some((t) => fn(String(t)));
  const lats = variables.filter((v) => seenBy(v, validatorSeesLatitude));
  const lngs = variables.filter((v) => seenBy(v, validatorSeesLongitude));
  for (const v of variables) {
    const lat = isLatitudeName(v.variable) && !seenBy(v, validatorSeesLatitude);
    const lng = isLongitudeName(v.variable) && !seenBy(v, validatorSeesLongitude);
    if (lat || lng) warnings.push(`${yamlFile}: variable ${v.variable} matches the ${lat ? 'latitude' : 'longitude'} inference rule but not the validator rule; inference would set it up but validate() would not see it`);
  }
  if (lats.length > 1) errors.push(`${yamlFile}: more than one latitude column (${lats.map((v) => v.variable).join(', ')})`);
  if (lngs.length > 1) errors.push(`${yamlFile}: more than one longitude column (${lngs.map((v) => v.variable).join(', ')})`);
  if (lats.length === 1 && lngs.length === 1) {
    for (const [axis, v] of [['latitude', lats[0]], ['longitude', lngs[0]]]) {
      const want = GEO[axis];
      const bad = [['stable_id', want.stableId], ['data_type', want.dataType], ['display_type', want.displayType]].filter(([k, x]) => v[k] !== x);
      for (const [k, x] of bad) errors.push(`${yamlFile}: ${axis} column ${v.variable} needs ${k} ${x} (found ${JSON.stringify(v[k])})`);
    }
  } else if (lats.length + lngs.length === 1) {
    const v = lats[0] || lngs[0];
    warnings.push(`${yamlFile}: variable ${v.variable} looks like a ${lats.length ? 'latitude' : 'longitude'} with no partner; check for a mislabelled coordinate`);
  }
  const geohash = variables.filter((v) => GEO.geohashColumns.includes(v.variable));
  if (geohash.length) warnings.push(`${yamlFile}: ${geohashWarning()} (${geohash.map((v) => v.variable).join(', ')})`);
}

// Column layout of one entity TSV against its YAML. Returns { idIndex, ancIndex, varIndex } or null.
function checkColumns(e, errors, warnings) {
  const { tsvFile, yamlFile, table, meta } = e;
  const headers = table.headers;
  const markerAt = headers.findIndex((h) => h.endsWith(MARKER));
  if (markerAt < 0) {
    errors.push(`${tsvFile}: transposed or malformed TSV (no \`\\\\ Descriptors\` marker in the header row); validate in mode 2`);
    return null;
  }
  const names = headers.map((h, i) => (i === markerAt ? h.slice(0, -MARKER.length) : h));
  const seen = new Set();
  for (const n of names) {
    if (seen.has(n)) errors.push(`${tsvFile}: duplicate column ${n}`);
    seen.add(n);
    if (!isValidColumnName(n)) warnings.push(`${tsvFile}: column name ${JSON.stringify(n)} is not a plain identifier (letters, digits, underscore, starting with a letter)`);
  }
  const index = new Map(names.map((n, i) => [n, i]));
  const ownName = e.own?.id_column;
  if (e.own && names[markerAt] !== ownName) errors.push(`${tsvFile}: the Descriptors column is ${names[markerAt]} but ${yamlFile} gives the entity's own ID as ${ownName}`);
  const ymlCols = new Map();
  for (const c of e.ids) ymlCols.set(c.id_column, 'id_columns');
  for (const v of asList(meta.variables)) if (isObj(v)) ymlCols.set(v.variable, 'variables');
  for (const n of names) if (!ymlCols.has(n)) errors.push(`${tsvFile}: column ${n} is not in ${yamlFile}`);
  for (const [n, where] of ymlCols) if (!index.has(n)) errors.push(`${yamlFile}: ${where === 'id_columns' ? 'id_column' : 'variable'} ${n} is not in ${tsvFile}`);
  return { markerAt, index };
}

function checkRows(e, layout, entities, errors, warnings) {
  const { tsvFile, table } = e;
  const { markerAt, index } = layout;
  const { report, flush } = limiter(errors);
  const rows = table.rows;
  const ownIds = new Set();
  const label = (r) => (rows[r][markerAt] === '' ? `row ${r + 2}` : rows[r][markerAt]);

  for (let r = 0; r < rows.length; r++) {
    const id = rows[r][markerAt];
    if (id === '') report(`${tsvFile}: empty ID`, `${tsvFile}: row ${r + 2}: empty ${e.own?.id_column ?? 'ID'}`);
    else if (ownIds.has(id)) report(`${tsvFile}: duplicate ID`, `${tsvFile}: ${id}: duplicate ID in ${e.own?.id_column ?? 'ID column'}`);
    else ownIds.add(id);
  }
  e.idSet = ownIds;

  // Ancestor IDs must exist in the ancestor's own ID column (checked after all entities are loaded)
  e.pending = () => {
    for (const c of e.ancestors) {
      const anc = entities.get(c.entity_name);
      const col = index.get(c.id_column);
      if (!anc?.idSet || col === undefined) continue;
      for (let r = 0; r < rows.length; r++) {
        const v = rows[r][col];
        if (v === '') report(`${tsvFile}: ${c.id_column}`, `${tsvFile}: ${label(r)}: ${c.id_column} is empty`);
        else if (!anc.idSet.has(v)) report(`${tsvFile}: ${c.id_column} orphan`, `${tsvFile}: ${label(r)}: ${c.id_column} ${v} not found in ${c.entity_name} (entity-${c.entity_name}.tsv)`);
      }
    }
    flush();
  };

  for (const v of asList(e.meta.variables)) {
    if (!isObj(v)) continue;
    const col = index.get(v.variable);
    if (col === undefined) continue;
    const levels = asList(v.ordinal_levels).map(String);
    const needsParse = ['date', 'integer', 'number', 'longitude'].includes(v.data_type) || v.display_type === 'latitude';
    if (!needsParse && !(v.data_shape === 'ordinal' && levels.length)) continue;
    const delim = v.is_multi_valued === true && typeof v.multi_value_delimiter === 'string' && v.multi_value_delimiter !== '' ? v.multi_value_delimiter : null;
    for (let r = 0; r < rows.length; r++) {
      const cell = rows[r][col];
      if (isMissing(cell)) continue;
      for (const value of delim ? cell.split(delim) : [cell]) {
        const problem = needsParse ? valueProblem(value, v)
          : levels.includes(value) ? null : 'is not in ordinal_levels';
        if (problem) report(`${tsvFile}: ${v.variable}`, `${tsvFile}: ${label(r)}: ${v.variable} value ${JSON.stringify(value)} ${problem}`);
      }
    }
  }
  flush();
}

/** Check an STF directory. Returns { errors, warnings }. */
export function checkStf(dir) {
  const errors = [];
  const warnings = [];
  if (!statSync(dir, { throwIfNoEntry: false })?.isDirectory()) {
    return { errors: [`${dir}: not a directory`], warnings };
  }
  const loaded = loadStudy(dir, errors);
  checkNotes(dir, warnings);
  if (!loaded) return { errors, warnings };
  const { entities } = loaded;

  checkTree(entities, errors);
  for (const e of entities.values()) {
    checkVariableMeta(e, errors);
    checkGeoMeta(e, errors, warnings);
    const layout = checkColumns(e, errors, warnings);
    if (layout) checkRows(e, layout, entities, errors, warnings);
  }
  for (const e of entities.values()) e.pending?.();
  return { errors, warnings };
}
