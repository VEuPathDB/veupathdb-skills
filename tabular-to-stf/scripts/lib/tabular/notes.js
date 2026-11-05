/**
 * curation-notes.md from the spec and the transform log: what was received,
 * the entity tree, every change (as replayable pseudo-code), what was flagged
 * and decided, and validation. Pure.
 */

// The copy of the spec that render-stf.js saves in the STF directory
export const SAVED_SPEC = 'curation-spec.json';

const q = (s) => JSON.stringify(s);
const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;
const COUNTED = ['trim', 'blank-placeholders', 'map-values', 'parse-dates'];

function columnsTarget(t) {
  if (!t.columns) return `\`${t.entity}\` (all columns)`;
  if (t.columns.length === 1) return `\`${t.entity}.${t.columns[0]}\``;
  return `\`${t.entity}\` (columns ${t.columns.map((c) => `\`${c}\``).join(', ')})`;
}

const pairs = (map) => Object.entries(map).map(([from, to]) => `${q(from)} → ${q(to)}`).join(', ');

// { target, text } for one transform, e.g. `participant.age`: "80+" → "80" (row P012)
function describe(t) {
  switch (t.op) {
    case 'trim': return { target: columnsTarget(t), text: 'trim whitespace' };
    case 'blank-placeholders': return { target: columnsTarget(t), text: `blank ${t.values.map(q).join(', ')}` };
    case 'map-values': return { target: `\`${t.entity}.${t.column}\``, text: pairs(t.map) };
    case 'rename-column': return { target: `\`${t.entity}.${t.from}\``, text: `rename to ${q(t.to)}` };
    case 'replace-cells': {
      const groups = new Map();
      for (const c of t.cells) {
        const k = `${q(c.from)} → ${q(c.to)}`;
        groups.set(k, [...(groups.get(k) || []), c.id]);
      }
      const text = [...groups].map(([k, ids]) => `${k} (${ids.length === 1 ? 'row' : 'rows'} ${ids.join(', ')})`).join('; ');
      return { target: `\`${t.entity}.${t.column}\``, text };
    }
    case 'parse-dates': return { target: `\`${t.entity}.${t.column}\``, text: `parse dates ${t.format} → YYYY-MM-DD` };
    case 'derive-column': {
      const map = Object.keys(t.map).length ? `${pairs(t.map)}, otherwise ${q(t.default)}` : `always ${q(t.default)}`;
      return { target: `\`${t.entity}.${t.column}\``, text: `new column from \`${t.from}\`: ${map}` };
    }
    case 'drop-column': return { target: `\`${t.entity}.${t.column}\``, text: 'drop column' };
    default: return { target: `\`${t.entity}\``, text: t.op };
  }
}

const MAX_IDS = 10;

// " (rows A, B and 3 more)" for a user change; auto changes keep counts only, whatever their size.
function rowIds(t, entry) {
  if (t.approval !== 'user' || !entry?.ids?.length) return '';
  const shown = entry.ids.slice(0, MAX_IDS).join(', ');
  const more = entry.ids.length > MAX_IDS ? ` and ${entry.ids.length - MAX_IDS} more` : '';
  return ` (${entry.ids.length === 1 ? 'row' : 'rows'} ${shown}${more})`;
}

function line(t, entry) {
  const { target, text } = describe(t);
  const count = entry && COUNTED.includes(t.op) ? `, ${plural(entry.cellsChanged, 'cell')} changed${rowIds(t, entry)}` : '';
  const instead = t.approval === 'rejected' ? ` Instead: ${t.instead}` : '';
  return `- ${target}: ${text}${count}. Reason: ${t.reason}${instead}`;
}

const bullets = (items) => (items.length ? items.map((x) => `- ${x}`).join('\n') : 'None.');

/**
 * `sources`: [{ entity?, path, rows? }], the input files as the notes should name them.
 * `decisions`: extra lines for Decisions and answers (from the renderer).
 */
export function renderNotes(spec, log, { sources, decisions = [] } = {}) {
  const transforms = spec.transforms || [];
  const notes = spec.notes || {};
  const entities = spec.entities;
  const src = sources || entities.map((e) => ({ entity: e.name, path: e.file }));
  const byEntity = new Map(src.filter((s) => s.entity).map((s) => [s.entity, s]));
  const out = [
    `# Curation notes: ${spec.study.name}`, '',
    `This directory was rendered from [${SAVED_SPEC}](${SAVED_SPEC}), the curation spec that records every change below. ` +
      `To re-render it, run the \`tabular-to-stf\` skill's \`scripts/render-stf.js ${SAVED_SPEC} <this directory>\`.`, '',
    '## Study', ''
  ];

  out.push(`- Name: ${spec.study.name}`);
  if (spec.study.description) out.push(`- Description: ${spec.study.description}`);
  out.push('- Source files:');
  for (const s of src) out.push(`  - \`${s.path}\`${s.rows !== undefined ? ` (${plural(s.rows, 'row')})` : ''}`);
  if (entities.some((e) => e.geo)) out.push('', 'Before `eda` validation or export, run `map_entities(study, infer_geo_variables_for_eda)`');

  out.push('', '## Entity tree', '');
  const visit = (e, depth) => {
    const from = byEntity.get(e.name)?.path ?? e.file;
    const link = e.parent !== undefined ? `, child of \`${e.parent}\` via \`${e.parentColumn}\`` : '';
    out.push(`${'  '.repeat(depth)}- \`${e.name}\` (${e.displayNamePlural}): \`${from}\`, ID \`${e.idColumn}\`${link}`);
    for (const c of entities) if (c.parent === e.name) visit(c, depth + 1);
  };
  const root = entities.find((e) => e.parent === undefined);
  if (root) visit(root, 0);

  const entries = log.map((entry) => ({ entry, t: transforms[entry.index] }));
  const pick = (approval) => entries.filter((x) => x.t.approval === approval);

  out.push('', '## Routine normalisation', '');
  const auto = pick('auto');
  out.push(auto.length ? auto.map(({ t, entry }) => line(t, entry)).join('\n') : 'None.');

  out.push('', '## Data changes', '');
  const user = pick('user');
  out.push(user.length ? user.map(({ t, entry }) => line(t, entry)).join('\n') : 'None.');
  const proposed = pick('proposed');
  if (proposed.length) out.push('', 'Proposed, not applied:', '', proposed.map(({ t }) => line(t)).join('\n'));
  const rejected = pick('rejected');
  if (rejected.length) out.push('', 'Rejected:', '', rejected.map(({ t }) => line(t)).join('\n'));

  out.push('', '## Flagged, not changed', '');
  out.push(bullets([...(notes.flagged || []), ...(notes.pii || []).map((p) => `PII: ${p}`)]));

  out.push('', '## Decisions and answers', '');
  out.push(bullets([...(notes.decisions || []), ...decisions]));

  out.push('', '## Validation', '');
  out.push(notes.validation && notes.validation.length ? bullets(notes.validation) : 'Not run (mode 1)');
  return `${out.join('\n')}\n`;
}
