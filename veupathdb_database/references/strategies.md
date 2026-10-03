# Strategies, steps, and the spec format

## WDK model (upstream truth)

- A STEP = searchName + searchConfig{parameters}. Step kind is determined by
  how many input-step params its search declares: 0 = leaf, 1 = transform,
  2 = combine (boolean).
- A STRATEGY = name + stepTree. Tree nodes carry ONLY {stepId, primaryInput?,
  secondaryInput?}. Parameters live on steps; wiring lives in the tree.
- A step outside a strategy cannot be run; deleting a step inside one is a
  409. This CLI always creates steps and immediately places them in a
  strategy.
- Boolean searches are per record type, named `boolean_question_*` (e.g.
  boolean_question_TranscriptRecordClasses_TranscriptRecordClass for
  transcript). Operand params bq_left_op*/bq_right_op* are input-step (sent
  ""); bq_operator ∈ UNION, INTERSECT, MINUS (left minus right), RMINUS,
  LONLY, RONLY.

## The create-strategy --spec format

    {"leaf":      {"search": "GenesByMolecularWeight",
                   "params": {"organism": ["Plasmodium falciparum 3D7"],
                              "min_molecular_weight": "100000"}}}
    {"combine":   {"operator": "INTERSECT", "left": <node>, "right": <node>}}
    {"transform": {"search": "GenesByOrthologs", "params": {...},
                   "input": <node>}}

Params omitted or null take the search's defaults (they're in the sheet's
params_template — disclose applied defaults to the user). Steps are created
bottom-up; the strategy is created last with the assembled stepTree; each
create is single-attempt (no retry-duplication).

## Structure semantics (from pathfinder's FRAME rules)

- Alternative evidence for the same property → UNION those searches.
- Distinct required properties → INTERSECT.
- A property with multiple evidence sources gets its OWN nested branch:
  A ∩ (B ∪ C) is not (A ∩ B) ∪ C.
- Few, broad criteria beat many narrow ones — ANDing many filters returns 0.
- Any search with an input-step param MUST be a transform node; standalone it
  makes WDK reject the whole strategy.

## Reading results

- Counts: displayViewTotalCount (genes) → viewTotalCount → displayTotalCount →
  totalCount (transcripts) — first present wins; all absent = "unmeasured",
  NEVER zero. estimatedSize -1 or absent likewise means unmeasured.
- The returned `url` opens the strategy on the website — always hand it to the
  user.
- Record ids are composite: gene_source_id + source_id + project_id.
