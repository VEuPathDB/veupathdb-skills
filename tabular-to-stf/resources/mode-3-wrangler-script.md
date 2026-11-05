# Mode 3: a study-wrangler script (not yet available)

Mode 3 is not implemented. If a user asks for it, tell them it is not available
yet, and offer mode 1 (and mode 2 if a container engine is present) instead.
This page records what mode 3 is meant to be, so that modes 1 and 2 do not
grow in its way.

## Intent

In mode 3, the model writes an R script that builds the study with
study-wrangler's own functions, then runs it in the pinned container. Those
functions include `entity_from_file()`, the entity and variable modifiers,
`study()`, `validate()` and `export_to_stf()`. The script is the curation
record: re-running it reproduces the STF from the raw files.

It is for data that the curation spec cannot express without growing a new
transform for every case. Examples are reshaping a wide table into a long
one, joining or splitting files into entities, and computed variables.
Studies that a curator will maintain in R also benefit.

## Prerequisites

- **study-wrangler self-documentation good enough for an LLM to write
  wrangler scripts.** That means function reference and worked examples
  covering loading, entity and variable metadata, the variable tree, geo
  inference and validation, and the errors to expect. The bundled STF
  docs ([Study-Transfer-Format-STF.md](stf/Study-Transfer-Format-STF.md),
  [metadata-fields.md](stf/metadata-fields.md)) describe the output format,
  not the R API.
- **Methods for any gaps.** Where the documentation is thin, the method is
  to read the package source in the container, or to run small probes
  there, through a bundled runner. Never run `docker` or `podman` directly,
  and never pull images.
- **A container runner for an arbitrary script.** It would be like
  `validate-stf-in-container.js`, but it would mount a work directory
  writable as the invoking user, so that `export_to_stf()` can write its
  output.

## How it relates to the shared pieces

- **Bundled STF docs.** These are the same files, pinned to the same
  study-wrangler version.
- **`check-stf.js`.** Mode 3 output is STF, so the same checks apply after
  the script runs. Then mode 2 validation follows.
- **`curation-notes.md` conventions.** These are the same sections. The
  script's steps are the replayable record of "Data changes", and the notes
  point to the script.
- **The curation spec.** A mode 1 spec and its ordered transform list can
  seed a wrangler script, since each transform maps onto a few lines of R.
  But mode 3 does not depend on having one. It can start from the raw files
  alone, or from a `raw-data/` folder written by mode 1.

Mode 3 is a **parallel route**, not a later stage. Nothing in modes 1 and 2
assumes that mode 3 will run after them, and their output is complete without
it.
