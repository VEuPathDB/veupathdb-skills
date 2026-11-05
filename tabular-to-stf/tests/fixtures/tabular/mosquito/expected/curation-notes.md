# Curation notes: Vallée du Kou Anopheles insecticide resistance survey

This directory was rendered from [curation-spec.json](curation-spec.json), the curation spec that records every change below. To re-render it, run the `tabular-to-stf` skill's `scripts/render-stf.js curation-spec.json <this directory>`.

## Study

- Name: Vallée du Kou Anopheles insecticide resistance survey
- Description: Synthetic entomological survey: mosquito collections at ten sites, species identification and insecticide resistance assays on the mosquitoes caught.
- Source files:
  - `raw-data/collection_sites.tsv` (10 rows)
  - `raw-data/collections.tsv` (12 rows)
  - `raw-data/samples.tsv` (15 rows)
  - `raw-data/assays.tsv` (15 rows)

Before `eda` validation or export, run `map_entities(study, infer_geo_variables_for_eda)`

## Entity tree

- `site` (Collection sites): `raw-data/collection_sites.tsv`, ID `site_id`
  - `collection` (Collections): `raw-data/collections.tsv`, ID `collection_id`, child of `site` via `site_id`
    - `sample` (Mosquito pools): `raw-data/samples.tsv`, ID `sample_id`, child of `collection` via `collection_id`
      - `assay` (Assays): `raw-data/assays.tsv`, ID `assay_id`, child of `sample` via `sample_id`

## Routine normalisation

- `collection.date`: rename to "collection date". Reason: A plain `date` header does not say which date.

## Data changes

- `sample.species`: "Anopheles gambie" → "Anopheles gambiae", 1 cell changed (row S007). Reason: Misspelling of Anopheles gambiae.

Proposed, not applied:

- `assay.mortality %`: "105" → "100" (row A05). Reason: Mortality above 100% is impossible; probably a corrected-mortality rounding error. Waiting for the provider.

## Flagged, not changed

- `assay.mortality_pct`: A05 is 105%. Left as is until the provider answers (see the proposed change).

## Decisions and answers

- Each row of samples.tsv is a pool of mosquitoes of one species and sex from one collection, so the entity is called Mosquito pool.

## Validation

- study-wrangler 1.0.54: `validate(study, profiles = c("baseline", "eda"))` after `map_entities(study, infer_geo_variables_for_eda)` passed.
