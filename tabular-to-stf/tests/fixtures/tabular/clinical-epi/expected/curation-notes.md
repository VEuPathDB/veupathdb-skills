# Curation notes: Lake Victoria household malaria survey

This directory was rendered from [curation-spec.json](curation-spec.json), the curation spec that records every change below. To re-render it, run the `tabular-to-stf` skill's `scripts/render-stf.js curation-spec.json <this directory>`.

## Study

- Name: Lake Victoria household malaria survey
- Description: Synthetic cross-sectional survey of villages, households and participants near Lake Victoria, with one or two blood samples per participant.
- Source files:
  - `raw-data/villages.csv` (10 rows)
  - `raw-data/households.csv` (12 rows)
  - `raw-data/participants.csv` (16 rows)
  - `raw-data/samples.csv` (18 rows)
  - `raw-data/data-dictionary.md`

Before `eda` validation or export, run `map_entities(study, infer_geo_variables_for_eda)`

## Entity tree

- `village` (Villages): `raw-data/villages.csv`, ID `village_id`
  - `household` (Households): `raw-data/households.csv`, ID `household_id`, child of `village` via `village_id`
    - `participant` (Participants): `raw-data/participants.csv`, ID `participant_id`, child of `household` via `household_id`
      - `sample` (Blood samples): `raw-data/samples.csv`, ID `sample_id`, child of `participant` via `participant_id`

## Routine normalisation

- `household.number of rooms`: blank "NA", 1 cell changed. Reason: NA marks a missing room count.
- `participant.Bednet use`: trim whitespace, 2 cells changed. Reason: Some bednet answers have a trailing space.
- `participant.Bednet use`: "y" → "Yes", "yes" → "Yes", 5 cells changed. Reason: Spelling and case variants of Yes.
- `participant.Occupation`: blank "N/A", 2 cells changed. Reason: N/A marks a missing occupation.
- `sample.Malaria RDT result`: "pos" → "Positive", "neg" → "Negative", 2 cells changed. Reason: Abbreviations of Positive and Negative.

## Data changes

- `participant.Participant name`: drop column. Reason: Personal names are identifying and not needed for analysis.
- `participant.Sex`: "Feamle" → "Female", 1 cell changed (row P007). Reason: Typo for Female.
- `participant.age_censored`: new column from `Age (years)`: "80+" → "Yes", otherwise "No". Reason: Keep the information that the age was top-coded before making the age numeric.
- `participant.Age (years)`: "80+" → "80" (row P012). Reason: Ages of 80 and over were recorded as 80+; record them as 80 so age is an integer, flagged by age_censored.
- `participant.Enrolment date`: parse dates DD/MM/YYYY → YYYY-MM-DD, 16 cells changed (rows P001, P002, P003, P004, P005, P006, P007, P008, P009, P010 and 6 more). Reason: Dates were given day first; STF needs ISO-8601.

Rejected:

- `participant.Weight (kg)`: "250" → "25.0" (row P009). Reason: A weight of 250 kg looks like a slipped decimal point. Instead: Kept 250 and flagged it for the provider to confirm.

## Flagged, not changed

- `participant.weight`: P009 weighs 250 kg, which is implausible for a height of 163 cm. Asked the provider.
- PII: `participants.csv` column `Participant name` holds full names; dropped from the STF but still present in `raw-data/`.

## Decisions and answers

- The study has no separate visit entity: each sample is linked directly to its participant (provider confirmed).
- `village.lon` is the longitude; written as `longitude` so that both EDA's inference and its validator recognise it.
- `village.established_market`: provider_label set to "Established market" (original header "Long-standing market").

## Validation

Not run (mode 1)
