/**
 * Applies the spec's ordered transforms to the input tables. Works on copies;
 * inputs are never modified. `proposed` and `rejected` transforms are logged
 * but not applied.
 *
 * The log counts changed cells for every transform. For `user` transforms it
 * also lists `ids`, the IDs of the rows with a changed cell, in row order; not
 * for `auto` ones, which may touch millions of rows.
 *
 * Row IDs (replace-cells, parse-dates errors, log ids) are the values in the
 * entity's idColumn, which the spec names as it is *after* renames. A transform
 * that runs before the producing rename-column finds the column under its
 * pre-rename name instead.
 */

const SKIPPED = ['proposed', 'rejected'];

function copyTable(t) {
  return { headers: t.headers.slice(), rows: t.rows.map((r) => r.slice()) };
}

function describe(entity, index, op) {
  return `entity "${entity}", transforms[${index}] (${op})`;
}

function colIndex(table, name, entity, index, op) {
  const i = table.headers.indexOf(name);
  if (i < 0) throw new Error(`${describe(entity, index, op)}: column ${JSON.stringify(name)} not found`);
  return i;
}

// idColumn's current index, following renames in the spec that have not run yet.
// A name seen twice means the renames form a cycle (or a no-op), so the column is not there.
function idIndex(table, idColumn, renames) {
  const seen = new Set();
  for (let name = idColumn; !seen.has(name); ) {
    const i = table.headers.indexOf(name);
    if (i >= 0) return i;
    seen.add(name);
    const r = renames.find((x) => x.to === name);
    if (!r) return -1;
    name = r.from;
  }
  return -1;
}

function dateParser(format) {
  const tokens = { YYYY: '(\\d{4})', DD: '(\\d{2})', MM: '(\\d{2})', D: '(\\d{1,2})', M: '(\\d{1,2})' };
  const order = [];
  let re = '';
  for (let i = 0; i < format.length;) {
    const tok = ['YYYY', 'DD', 'MM', 'D', 'M'].find((t) => format.startsWith(t, i));
    if (tok) {
      re += tokens[tok];
      order.push(tok[0]);
      i += tok.length;
    } else {
      re += format[i].replace(/[.*+?^${}()|[\]\\\/-]/g, '\\$&');
      i++;
    }
  }
  const rx = new RegExp(`^${re}$`);
  return (value) => {
    const m = rx.exec(value);
    if (!m) return null;
    const p = {};
    order.forEach((k, i) => { p[k] = Number(m[i + 1]); });
    if (p.Y === undefined || p.M === undefined || p.D === undefined) return null;
    const d = new Date(Date.UTC(p.Y, p.M - 1, p.D));
    if (d.getUTCFullYear() !== p.Y || d.getUTCMonth() !== p.M - 1 || d.getUTCDate() !== p.D) return null;
    return `${String(p.Y).padStart(4, '0')}-${String(p.M).padStart(2, '0')}-${String(p.D).padStart(2, '0')}`;
  };
}

function applyOne(t, index, table, idColumn, renames) {
  const where = describe(t.entity, index, t.op);
  const col = (name) => colIndex(table, name, t.entity, index, t.op);
  const cols = () => (t.columns ? t.columns.map(col) : table.headers.map((_, i) => i));
  // Changed-row IDs are kept only for user transforms (see the header comment).
  const track = t.approval === 'user';
  const idc = track ? idIndex(table, idColumn, renames) : -1;
  const changed = [];
  const noteRow = (row, r) => { if (track) changed.push(idc >= 0 ? row[idc] : `row ${r + 1}`); };
  const withIds = (result) => (track ? { ...result, ids: changed } : result);
  const mapCells = (indexes, fn) => {
    let n = 0;
    table.rows.forEach((row, r) => {
      let hit = false;
      for (const c of indexes) {
        const next = fn(row[c]);
        if (next !== row[c]) { row[c] = next; n++; hit = true; }
      }
      if (hit) noteRow(row, r);
    });
    return n;
  };
  switch (t.op) {
    case 'trim': return withIds({ cellsChanged: mapCells(cols(), (v) => v.trim()) });
    case 'blank-placeholders': return withIds({ cellsChanged: mapCells(cols(), (v) => (t.values.includes(v) ? '' : v)) });
    case 'map-values': {
      const c = col(t.column);
      return withIds({ column: t.column, cellsChanged: mapCells([c], (v) => (Object.hasOwn(t.map, v) ? t.map[v] : v)) });
    }
    case 'rename-column': {
      const c = col(t.from);
      if (t.from !== t.to && table.headers.includes(t.to)) throw new Error(`${where}: column ${JSON.stringify(t.to)} already exists`);
      table.headers[c] = t.to;
      return { column: t.to, cellsChanged: 0 };
    }
    case 'replace-cells': {
      const c = col(t.column);
      const rid = idIndex(table, idColumn, renames);
      if (rid < 0) throw new Error(`${where}: ID column ${JSON.stringify(idColumn)} not found`);
      const byId = new Map(table.rows.map((r) => [r[rid], r]));
      let n = 0;
      for (const cell of t.cells) {
        const row = byId.get(cell.id);
        if (!row) throw new Error(`${where}: row ID ${JSON.stringify(cell.id)} not found`);
        if (row[c] !== cell.from) throw new Error(`${where}: row ID ${JSON.stringify(cell.id)} column ${JSON.stringify(t.column)} is ${JSON.stringify(row[c])}, spec expects ${JSON.stringify(cell.from)} (stale spec?)`);
        if (cell.to !== row[c]) { row[c] = cell.to; n++; changed.push(cell.id); }
      }
      return withIds({ column: t.column, cellsChanged: n });
    }
    case 'parse-dates': {
      const c = col(t.column);
      const parse = dateParser(t.format);
      const rid = idIndex(table, idColumn, renames);
      const bad = [];
      const out = table.rows.map((row, r) => {
        if (row[c] === '') return '';
        const iso = parse(row[c]);
        if (iso === null) bad.push(rid >= 0 ? row[rid] : `row ${r + 1}`);
        return iso;
      });
      if (bad.length) throw new Error(`${where}: values in column ${JSON.stringify(t.column)} do not match format ${t.format} for row IDs: ${bad.join(', ')}`);
      let n = 0;
      table.rows.forEach((row, r) => { if (row[c] !== out[r]) { row[c] = out[r]; n++; noteRow(row, r); } });
      return withIds({ column: t.column, cellsChanged: n });
    }
    case 'derive-column': {
      const from = col(t.from);
      if (table.headers.includes(t.column)) throw new Error(`${where}: column ${JSON.stringify(t.column)} already exists`);
      table.headers.push(t.column);
      for (const row of table.rows) row.push(Object.hasOwn(t.map, row[from]) ? t.map[row[from]] : t.default);
      return { column: t.column, cellsChanged: 0 };
    }
    case 'drop-column': {
      const c = col(t.column);
      table.headers.splice(c, 1);
      for (const row of table.rows) row.splice(c, 1);
      return { column: t.column, cellsChanged: 0 };
    }
    default: throw new Error(`${where}: unknown op`);
  }
}

export function applyTransforms(tables, spec) {
  const out = new Map([...tables].map(([name, t]) => [name, copyTable(t)]));
  const idColumns = new Map((spec.entities || []).map((e) => [e.name, e.idColumn]));
  const log = [];
  (spec.transforms || []).forEach((t, index) => {
    const entry = { index, op: t.op, entity: t.entity, approval: t.approval, cellsChanged: 0 };
    if (t.column !== undefined) entry.column = t.column;
    log.push(entry);
    if (SKIPPED.includes(t.approval)) return;
    const table = out.get(t.entity);
    if (!table) throw new Error(`${describe(t.entity, index, t.op)}: no table for entity`);
    const later = spec.transforms.slice(index + 1).filter((x) => x.op === 'rename-column' && x.entity === t.entity && !SKIPPED.includes(x.approval));
    Object.assign(entry, applyOne(t, index, table, idColumns.get(t.entity), later));
  });
  return { tables: out, log };
}
