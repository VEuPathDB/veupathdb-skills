# Mode 2: validate and fix in a container

Mode 2 loads the STF directory with study-wrangler itself, in its pinned
container image (`veupathdb/study-wrangler:1.0.54`). It validates the study the
way VEuPathDB EDA does, then fixes what the validator reports. It runs after
mode 1, or on its own on an existing STF directory.

## Container safety

- **Always validate through `validate-stf-in-container.js`.** Never run
  `docker` or `podman` yourself, not even to list images.
- **Never pull an image without asking the user.** The script runs the
  container with `--pull=never`, so it never downloads anything. The pinned
  image must already be present.
- If the image is missing, the run ends `Result: load-error` and the output
  shows the engine's own error, such as `No such image` or `image not
  known`, with no marker line (no `STF_LOAD_ERROR:` or
  `STF_VALIDATION_ERROR:`). Tell the user the exact command,
  and let them decide. It is a download of about 6 GB.

  ```bash
  docker pull veupathdb/study-wrangler:1.0.54
  # or, with podman:
  podman pull docker.io/veupathdb/study-wrangler:1.0.54
  ```

- The STF directory is mounted read-only. The container cannot change your
  files.

## Running it

```bash
node scripts/validate-stf-in-container.js --detect
node scripts/validate-stf-in-container.js <stfDir>
node scripts/validate-stf-in-container.js <stfDir> --engine podman
```

`--detect` prints `docker`, `podman` or `none`. Without `--engine`, the
validator uses the first engine that answers, trying docker and then podman.
Allow a few minutes per run, because R and study-wrangler take time to start.

The container does three things:

1. `study_from_stf(dir, validate = FALSE)`.
2. `map_entities(study, infer_geo_variables_for_eda)`.
3. `validate(study, profiles = c("baseline", "eda"))`.

If validation fails, it runs a verbose validation of each entity, under an
`== entity: <name> ==` heading. The last line is `Result: <status>`.

| Exit | `Result:` | Meaning |
|---|---|---|
| 0 | `pass` | Loads and validates |
| 1 | `fail` | Loads, but validation reported problems. Read the per-entity output |
| 2 | `error` | With `STF_VALIDATION_ERROR: <message>`: the study loaded, but geo inference or `validate()` stopped with an R error instead of a verdict. Treat the message like a validation problem: it names what study-wrangler could not handle, such as a parent ID column it cannot join on. Run `check-stf.js`, which catches the known causes |
| 2 | `load-error` | With `STF_LOAD_ERROR: <message>`: `study_from_stf()` could not load the study. Without any marker line: the container ran no further than that, for example because the image is missing, the daemon is down or R failed to start. The engine's own message is in the output |
| 3 | | No docker or podman found. Mode 2 is not possible here |
| 1 | | With `Error: ...` on stderr and no `Result:`: bad arguments, or the directory does not exist |

## The loop

Each round runs these steps:

1. `node scripts/check-stf.js <stfDir>`. Fix any errors first. They are
   cheaper to find than a container run.
2. `node scripts/validate-stf-in-container.js <stfDir>`.
3. If the result is `pass`, stop.
4. Otherwise, sort each reported problem into one of two kinds:
   - **Metadata fixes**: change the spec (or, with no spec, the YAML) and
     apply the change. Record it in `notes.decisions`. Examples:
     - a wrong `data_type` or `data_shape` (`binary` with three values);
     - a missing `display_name`;
     - a `unit` on a string;
     - a `vocabularyOrder` value that does not occur;
     - an ordinal value missing from `ordinalLevels`;
     - a second latitude or longitude look-alike, which needs a rename or
       `providerLabel`, see
       [variable-metadata.md](variable-metadata.md#geocoordinates).
   - **Data fixes**: these follow the same approval rule as mode 1 (see
     [cleaning.md](cleaning.md)). Batch them per entity, propose a fix for
     each, and apply only what the user approves. Examples:
     - a coordinate out of range;
     - a row with only one of latitude and longitude;
     - a value that does not parse as its type.
5. Re-render (`node scripts/render-stf.js <stfDir>/curation-spec.json <stfDir>`),
   then go back to step 1.

Stop after **5 rounds**, or as soon as the only problems left are waiting for
the user. Then report to the user:

- what passed;
- what was fixed, in each round;
- each problem that remains, with your proposed fix.

After each container run, add an entry to `notes.validation`, as described
in [curation-notes.md](curation-notes.md), and re-render. Only the notes
change, so you do not need to validate again for that.

If a message is unclear, find the field in
[metadata-fields.md](stf/metadata-fields.md) or the format rules in
[Study-Transfer-Format-STF.md](stf/Study-Transfer-Format-STF.md) before you
change anything. Do not guess at a fix that changes data.

## An STF directory with no curation spec

When the user gives you an existing STF directory that has no
`curation-spec.json`, nothing can re-render it. In this case only, edit the
STF files directly:

- Make metadata fixes in the `entity-<name>.yaml` files. Make data fixes,
  once approved, in the `entity-<name>.tsv` files. Keep the TSVs
  tab-separated, and keep the `\\ Descriptors` marker on the ID header.
- Never change anything under `raw-data/`.
- Log every change in `curation-notes.md`. If it is missing, create it with
  the sections in [curation-notes.md](curation-notes.md). Otherwise, append
  to its sections. Write each data change as a replayable step, for example
  `participant.age: "80+" → 80 (row P012); add age_censored = Yes`. Record
  each container run under **Validation**.
- `check-stf.js` handles the standard layout of full STF only. For STF-lite
  or transposed entity files, it reports that it cannot check them. Rely on
  the container for those.

Do not write a curation spec for an existing directory unless the user asks
for one. That is mode 1 on its `raw-data/`, if the directory has it.
