# WDK parameters and vocabularies

Every parameter value is a STRING on the wire. `encode_params` handles the
conversions below; this doc explains what it does and why.

## Parameter types

string, number, date, timestamp, number-range, date-range,
single-pick-vocabulary, multi-pick-vocabulary, input-step, input-dataset,
filter. Numeric bounds (e.g. min_molecular_weight) are usually `string`
params — WDK rejects thousands separators; send `"10000"` not `"10,000"`.

## Semantics the sheet encodes

- `required` = NOT allowEmptyValue. `default` = initialDisplayValue (a real
  default, but not a promise the value is still valid — the count will tell).
- Hidden params (`isVisible: false`) are presentation-only: STILL required,
  STILL validated. The sheet omits them; encode_params submits their defaults.
- Multi-pick values are JSON arrays serialized to a string:
  `"[\"a\",\"b\"]"`. A single-pick given a 2-element array is a 500.
- `input-step` params are ALWAYS submitted as "" — the actual input step is
  wired via the strategy's stepTree, never via parameters.
- `input-dataset` params expect an uploaded numeric Dataset ID on the wire. When
  passed a list of IDs or a delimited string (e.g. `"AGAP001234, AGAP001235"`),
  `encode_params` automatically uploads them via `POST /users/current/datasets`
  and substitutes the assigned dataset ID. Passing a numeric string directly
  is also supported.

## Vocabularies

- Flat vocab: rows of [term, display, parent]. Term is what you submit.
- Tree vocab (displayType treeBox): nodes {data: {term, display}, children}.
  The synthetic root term `@@fake@@` is never a value.
- `countOnlyLeaves: true` + a PARENT term submitted directly = WDK silently
  selects NOTHING (0 rows). encode_params expands parents to their leaf
  descendants, mirroring the website's checkbox tree.
- Dependent vocabularies: a param listing others in `dependentParams` controls
  their vocabulary. Read the dependent's options only under bound parents —
  `param-options` uses parent defaults and says so in `context_note`; pass
  `--context parent=value` to change. After changing a parent value, re-read
  the dependent's options; previously valid values may be gone.
- Huge vocabularies (>200) are shortlisted in the sheet with a note; use
  `param-options SEARCH PARAM --query <keyword>` to find exact terms.
