/**
 * Renders a curation spec plus input tables to STF file texts: study.yaml,
 * entity-<name>.{tsv,yaml} and curation-notes.md. Pure; the CLI reads and
 * writes. Every problem found is collected and thrown as one RenderError.
 */

import { inferType, yamlScalar, toColumnName, uniqueColumnNames } from '../stf-common.js';
import { validateSpec } from './spec.js';
import { applyTransforms } from './transforms.js';
import { GEO, isLatitudeName, isLongitudeName, validatorSeesLatitude, validatorSeesLongitude } from './geo.js';
import { renderNotes } from './notes.js';

export class RenderError extends Error {
  constructor(messages) {
    super(messages.join('\n'));
    this.name = 'RenderError';
    this.messages = messages;
  }
}

const SKIPPED = ['proposed', 'rejected'];
const MAX_LISTED = 10;

const looksLat = (s) => isLatitudeName(s) || validatorSeesLatitude(s);
const looksLng = (s) => isLongitudeName(s) || validatorSeesLongitude(s);
const passesLat = (s) => isLatitudeName(s) && validatorSeesLatitude(s);
const passesLng = (s) => isLongitudeName(s) && validatorSeesLongitude(s);

const NUMBER = /^-?(0|[1-9]\d*)(\.\d+)?([eE][+-]?\d+)?$/;
function isIsoDate(v) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(v);
  if (!m) return false;
  const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
  return d.getUTCFullYear() === +m[1] && d.getUTCMonth() === +m[2] - 1 && d.getUTCDate() === +m[3];
}
// Leading zeros are refused for numbers: the loader reads such a column as text
const PARSES = {
  string: () => true,
  integer: (v) => /^-?(0|[1-9]\d*)$/.test(v),
  number: (v) => NUMBER.test(v),
  longitude: (v) => NUMBER.test(v),
  date: isIsoDate,
};

// Entity names in pre-order from the root, siblings in spec order.
function treeOrder(entities) {
  const out = [];
  const visit = (name) => {
    out.push(name);
    for (const e of entities) if (e.parent === name) visit(e.name);
  };
  const root = entities.find((e) => e.parent === undefined);
  if (root) visit(root.name);
  return out;
}

// Current header -> original input header (null for derived columns), following applied transforms.
function originalHeaders(entity, inputHeaders, transforms) {
  const origin = new Map(inputHeaders.map((h) => [h, h]));
  for (const t of transforms) {
    if (t.entity !== entity || SKIPPED.includes(t.approval)) continue;
    if (t.op === 'rename-column') { origin.set(t.to, origin.get(t.from)); origin.delete(t.from); }
    if (t.op === 'derive-column') origin.set(t.column, null);
    if (t.op === 'drop-column') origin.delete(t.column);
  }
  return origin;
}

// The parent ID column (`fixed`) keeps the parent's own ID name, since study-wrangler joins on it.
// Explicit names are kept too (a clash with either is an error); auto names get _2, _3, ... suffixes.
function assignNames(cols, entity, errors) {
  const byName = new Map();
  const kept = [...cols.filter((x) => x.fixed), ...cols.filter((x) => x.explicit && !x.fixed)];
  for (const c of kept) {
    const other = byName.get(c.name);
    if (other?.fixed) errors.push(`${entity}: output column name "${c.name}" for column "${c.header}" is the ID column name of parent entity "${other.entity}"; the parent ID column must keep that name, so choose another`);
    else if (other) errors.push(`${entity}: output column name "${c.name}" is used by both "${other.header}" and "${c.header}"`);
    else byName.set(c.name, c);
  }
  const order = [...kept, ...cols.filter((x) => !x.explicit && !x.fixed)];
  const unique = uniqueColumnNames(order.map((c) => c.name));
  order.forEach((c, i) => { if (!c.explicit && !c.fixed) c.name = unique[i]; });
}

function yamlList(key, items, indent) {
  return `${indent}${key}:\n${items.map((x) => `${indent}  - ${yamlScalar(x)}\n`).join('')}`;
}

function variableYaml(v) {
  let out = `  - variable: ${yamlScalar(v.variable)}\n`;
  if (v.provider_label != null) out += yamlList('provider_label', [v.provider_label], '    ');
  out += `    display_name: ${yamlScalar(v.display_name)}\n`;
  if (v.definition !== undefined) out += `    definition: ${yamlScalar(v.definition)}\n`;
  out += `    data_type: ${v.data_type}\n`;
  out += `    data_shape: ${v.data_shape}\n`;
  if (v.unit !== undefined) out += `    unit: ${yamlScalar(v.unit)}\n`;
  if (v.ordinal_levels) out += yamlList('ordinal_levels', v.ordinal_levels, '    ');
  if (v.vocabulary_order) out += yamlList('vocabulary_order', v.vocabulary_order, '    ');
  if (v.is_multi_valued !== undefined) out += `    is_multi_valued: ${v.is_multi_valued ? 'true' : 'false'}\n`;
  if (v.multi_value_delimiter !== undefined) out += `    multi_value_delimiter: ${yamlScalar(v.multi_value_delimiter)}\n`;
  if (v.parent_category !== undefined) out += `    parent_category: ${yamlScalar(v.parent_category)}\n`;
  if (v.stable_id !== undefined) out += `    stable_id: ${yamlScalar(v.stable_id)}\n`;
  if (v.display_type !== undefined) out += `    display_type: ${v.display_type}\n`;
  return out;
}

function categoryYaml(c) {
  let out = `  - category: ${yamlScalar(c.category)}\n`;
  out += `    display_name: ${yamlScalar(c.displayName)}\n`;
  if (c.definition !== undefined) out += `    definition: ${yamlScalar(c.definition)}\n`;
  if (c.parentCategory !== undefined) out += `    parent_category: ${yamlScalar(c.parentCategory)}\n`;
  return out;
}

function entityYaml(e, idCols, variables) {
  let out = `name: ${e.name}\ndisplay_name: ${yamlScalar(e.displayName)}\ndisplay_name_plural: ${yamlScalar(e.displayNamePlural)}\n\nid_columns:\n`;
  for (const c of idCols) {
    out += `  - id_column: ${yamlScalar(c.name)}\n    entity_name: ${c.entity}\n`;
    if (c.level) out += `    entity_level: ${c.level}\n`;
    if (c.label != null) out += yamlList('provider_label', [c.label], '    ');
  }
  out += `\nvariables:\n${variables.map(variableYaml).join('')}\n`;
  const cats = e.categories || [];
  out += cats.length ? `categories:\n${cats.map(categoryYaml).join('')}` : 'categories: []\n';
  return out;
}

// Coordinate-like columns outside the geo pair. Every column is checked by name and by provider label.
function checkGeo(e, cols, geoCols, errors) {
  const others = cols.filter((c) => !geoCols.includes(c));
  if (e.geo) {
    for (const c of others) {
      const axis = (s) => (looksLat(s) ? 'latitude' : looksLng(s) ? 'longitude' : null);
      const where = `${e.name}.${c.name}`;
      if (axis(c.name)) {
        errors.push(`${where}: name "${c.name}" looks like a ${axis(c.name)} to EDA, but ${e.name} already has geo coordinates; give it another name with a rename-column transform or the variable's name`);
      } else if (c.label != null && axis(c.label)) {
        errors.push(`${where}: provider_label "${c.label}" looks like a ${axis(c.label)} to the EDA validator, but ${e.name} already has geo coordinates; set the variable's providerLabel to a wording without it`);
      }
    }
    return;
  }
  const hits = [];
  for (const c of cols) {
    const texts = [c.name, ...(c.label != null ? [c.label] : [])];
    if (texts.some(looksLat)) hits.push(c.name);
    if (texts.some(looksLng)) hits.push(c.name);
  }
  if (hits.length >= 2) {
    errors.push(`${e.name}: ${hits.length} columns look like coordinates (${hits.join(', ')}); EDA validation fails on more than one. Declare the pair as geo, or rename the others`);
  }
}

function renderEntity(e, spec, input, table, parent, errors, decisions) {
  const { headers, rows } = table;
  const at = (h) => headers.indexOf(h);
  const origin = originalHeaders(e.name, input.headers, spec.transforms || []);
  const startErrors = errors.length;

  const idIdx = at(e.idColumn);
  if (idIdx < 0) errors.push(`${e.name}: ID column "${e.idColumn}" not found after transforms`);
  const parentIdx = e.parent !== undefined ? at(e.parentColumn) : -1;
  if (e.parent !== undefined && parentIdx < 0) errors.push(`${e.name}: parent column "${e.parentColumn}" not found after transforms`);
  const idIdxs = [idIdx, parentIdx];

  const seen = new Set();
  const varCols = [];
  for (const v of e.variables) {
    const idx = at(v.column);
    if (idx < 0) { errors.push(`${e.name}: variable column "${v.column}" not found after transforms`); continue; }
    if (idIdxs.includes(idx)) { errors.push(`${e.name}: variable column "${v.column}" is an ID column`); continue; }
    if (seen.has(v.column)) { errors.push(`${e.name}: variable column "${v.column}" is listed twice`); continue; }
    seen.add(v.column);
    const label = v.providerLabel ?? origin.get(v.column);
    varCols.push({ v, idx, header: v.column, name: v.name ?? toColumnName(v.column), explicit: v.name !== undefined, label });
  }
  headers.forEach((h, i) => {
    if (!idIdxs.includes(i) && !seen.has(h)) errors.push(`unaccounted column ${e.name}.${h}: list it in variables or remove it with drop-column`);
  });
  if (errors.length > startErrors) return null;

  const geoCols = [];
  if (e.geo) {
    for (const [axis, passes] of [['latitude', passesLat], ['longitude', passesLng]]) {
      const c = varCols.find((x) => x.header === e.geo[axis]);
      if (!c) { errors.push(`${e.name}: geo.${axis} column "${e.geo[axis]}" must be listed in variables`); continue; }
      if (!passes(c.name)) {
        decisions.push(`\`${e.name}.${c.name}\` is the ${axis}; written as \`${axis}\` so that both EDA's inference and its validator recognise it.`);
        c.name = axis;
        c.explicit = true;
      }
      c.geo = axis;
      geoCols.push(c);
    }
  }

  const idCols = [];
  if (parent) idCols.push({ idx: parentIdx, header: e.parentColumn, name: parent.idName, explicit: false, fixed: true, entity: parent.name, level: -1, label: origin.get(e.parentColumn) });
  idCols.push({ idx: idIdx, header: e.idColumn, name: e.idName ?? toColumnName(e.idColumn), explicit: e.idName !== undefined, entity: e.name, label: origin.get(e.idColumn) });
  const cols = [...idCols, ...varCols];
  assignNames(cols, e.name, errors);
  checkGeo(e, cols, geoCols, errors);

  for (const c of varCols) {
    if (c.v.providerLabel !== undefined) {
      const was = origin.get(c.header);
      decisions.push(`\`${e.name}.${c.name}\`: provider_label set to "${c.v.providerLabel}" (${was == null ? 'derived column' : `original header "${was}"`}).`);
    }
  }

  const rowId = (r) => (rows[r][idIdx] === '' ? `row ${r + 1}` : rows[r][idIdx]);
  for (const c of cols) {
    const bad = [];
    for (let r = 0; r < rows.length; r++) if (/[\t\n\r]/.test(rows[r][c.idx])) bad.push(rowId(r));
    if (bad.length === 1) errors.push(`${e.name}.${c.header}: value in row ${bad[0]} contains a tab or line break`);
    else if (bad.length) errors.push(`${e.name}.${c.header}: values in rows ${bad.slice(0, MAX_LISTED).join(', ')}${bad.length > MAX_LISTED ? ', ...' : ''} contain a tab or line break`);
  }

  const variables = varCols.map((c) => {
    const v = c.v;
    const values = rows.map((r) => r[c.idx]);
    const g = c.geo ? GEO[c.geo] : null;
    const declared = g ? g.dataType : v.dataType;
    const dataType = declared ?? inferType(values).data_type;
    if (declared) {
      const bad = [];
      for (let r = 0; r < rows.length; r++) if (values[r] !== '' && !PARSES[declared](values[r])) bad.push(r);
      if (bad.length) {
        const listed = bad.slice(0, MAX_LISTED).map((r) => `${JSON.stringify(values[r])} (${rowId(r)})`).join(', ');
        errors.push(`${e.name}.${c.header}: declared ${declared} but ${bad.length} value${bad.length === 1 ? '' : 's'} do${bad.length === 1 ? 'es' : ''} not parse: ${listed}${bad.length > MAX_LISTED ? ', ...' : ''}`);
      }
    }
    return {
      variable: c.name,
      provider_label: c.label,
      display_name: v.displayName ?? c.label ?? c.name,
      definition: v.definition,
      data_type: dataType,
      data_shape: g ? 'continuous' : v.dataShape ?? (v.ordinalLevels ? 'ordinal' : dataType === 'string' ? 'categorical' : 'continuous'),
      unit: v.unit,
      ordinal_levels: v.ordinalLevels,
      vocabulary_order: v.vocabularyOrder,
      is_multi_valued: v.isMultiValued,
      multi_value_delimiter: v.multiValueDelimiter,
      parent_category: v.parentCategory,
      stable_id: g ? g.stableId : v.stableId,
      display_type: g ? g.displayType : v.displayType,
    };
  });

  const ownId = idCols[idCols.length - 1];
  const header = cols.map((c) => (c === ownId ? `${c.name} \\\\ Descriptors` : c.name));
  const out = [header.join('\t')];
  for (const row of rows) out.push(cols.map((c) => row[c.idx]).join('\t'));
  return { idName: ownId.name, tsv: `${out.join('\n')}\n`, yaml: entityYaml(e, idCols, variables) };
}

/**
 * Returns { files, log }. `tables` maps entity name to its input { headers, rows }.
 * `sourceDir` is how curation-notes.md refers to the input files' folder.
 */
export function renderStf(spec, tables, { sourceDir = 'raw-data' } = {}) {
  const specErrors = validateSpec(spec);
  if (specErrors.length) throw new RenderError(specErrors);
  const missing = spec.entities.filter((e) => !tables.has(e.name)).map((e) => `${e.name}: no input table`);
  if (missing.length) throw new RenderError(missing);

  let transformed;
  try {
    transformed = applyTransforms(tables, spec);
  } catch (err) {
    throw new RenderError([err.message]);
  }

  const errors = [];
  const decisions = [];
  const files = {};
  const done = new Map();
  const order = treeOrder(spec.entities);
  for (const name of order) {
    const e = spec.entities.find((x) => x.name === name);
    const parent = e.parent !== undefined ? done.get(e.parent) : null;
    if (e.parent !== undefined && !parent) continue; // the parent failed; its errors are already listed
    const r = renderEntity(e, spec, tables.get(name), transformed.tables.get(name), parent, errors, decisions);
    if (!r) continue;
    done.set(name, { name, idName: r.idName });
    files[`entity-${name}.tsv`] = r.tsv;
    files[`entity-${name}.yaml`] = r.yaml;
  }
  if (errors.length) throw new RenderError(errors);

  files['study.yaml'] = `name: ${yamlScalar(spec.study.name)}\nentities:\n${order.map((n) => `  - ${n}\n`).join('')}`;
  const sources = [
    ...spec.entities.map((e) => ({ entity: e.name, path: `${sourceDir}/${e.file}`, rows: tables.get(e.name).rows.length })),
    ...(spec.extraFiles || []).map((f) => ({ path: `${sourceDir}/${f}` })),
  ];
  files['curation-notes.md'] = renderNotes(spec, transformed.log, { sources, decisions });
  return { files, log: transformed.log };
}
