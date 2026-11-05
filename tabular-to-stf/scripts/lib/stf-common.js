/**
 * Helpers shared by the STF writers: type inference, YAML scalar quoting and
 * column naming. Pure.
 */

export function inferType(values) {
  const nonNull = values.filter(v => v !== null && v !== undefined && v !== '');
  if (nonNull.length === 0) return { data_type: 'string', data_shape: 'categorical' };
  // Leading zeros mark codes (007), not quantities
  if (nonNull.some(v => /^0\d/.test(String(v)))) return { data_type: 'string', data_shape: 'categorical' };
  if (nonNull.every(v => /^-?\d+$/.test(String(v)))) return { data_type: 'integer', data_shape: 'continuous' };
  if (nonNull.every(v => /^-?\d+(\.\d+)?([eE][+-]?\d+)?$/.test(String(v)))) return { data_type: 'number', data_shape: 'continuous' };
  if (nonNull.every(v => /^\d{4}-\d{2}-\d{2}$/.test(String(v)))) return { data_type: 'date', data_shape: 'continuous' };
  return { data_type: 'string', data_shape: 'categorical' };
}

// YAML is built by hand to stay dependency-free, so scalars are quoted here:
// single-quote style, whose only escape is doubling a literal single quote.
// Plain scalars a YAML 1.1 reader (R's yaml) may resolve to a number: decimals with an optional
// trailing dot, exponent or _ separators (1., 1e3, 1_000), hex/octal/binary (0x1F, 0o17, 0b101),
// sexagesimal (1:30), and .inf/.nan in any case and sign.
function looksNumeric(str) {
  return /^[-+]?(\d[\d_]*(\.[\d_]*)?|\.\d[\d_]*)([eE][-+]?\d+)?$/.test(str) ||
    /^[-+]?0(x[0-9a-f_]+|o[0-7_]+|b[01_]+)$/i.test(str) ||
    /^[-+]?\d[\d_]*(:[0-5]?\d)+(\.[\d_]*)?$/.test(str) ||
    /^[-+]?\.(inf|nan)$/i.test(str);
}

export function yamlScalar(value) {
  const str = String(value);
  // Control characters can't survive single quotes (YAML folds the line break), so double-quote them
  if (/[\n\r\t]/.test(str)) {
    const escaped = str.replace(/[\\"\n\r\t]/g, c => ({ '\\': '\\\\', '"': '\\"', '\n': '\\n', '\r': '\\r', '\t': '\\t' })[c]);
    return `"${escaped}"`;
  }
  const needsQuoting =
    str === '' ||
    /^\s|\s$/.test(str) ||
    /: |:$/.test(str) ||
    /\s#/.test(str) ||
    /^[-?:,\[\]{}#&*!|>'"%@`]/.test(str) ||
    /^(true|false|null|yes|no|on|off|y|n|~)$/i.test(str) ||
    looksNumeric(str);
  if (!needsQuoting) return str;
  return `'${str.replace(/'/g, "''")}'`;
}

// Names that need no quoting in R (and survive make.names), SQL or Python.
export function isValidColumnName(name) {
  return /^[A-Za-z][A-Za-z0-9_]*$/.test(name);
}

// snake_case: 'Age (years)' -> 'age_years'; 'x' prefix if empty or digit-led
export function toColumnName(header) {
  const name = String(header).toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
  return name === '' || /^\d/.test(name) ? `x${name}` : name;
}

// Keeps the first occurrence; later duplicates get _2, _3, ...
export function uniqueColumnNames(names) {
  const seen = new Set(names);
  const counts = new Map();
  const first = new Set();
  return names.map(n => {
    if (!first.has(n)) { first.add(n); return n; }
    let k = counts.get(n) || 1;
    let candidate;
    do { candidate = `${n}_${++k}`; } while (seen.has(candidate));
    counts.set(n, k);
    seen.add(candidate);
    return candidate;
  });
}
