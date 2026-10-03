# Silent-failure modes (WDK accepts your request; the science is wrong)

Each of these was learned the hard way in pathfinder and is machine-checked
there (docs/knowledge/wdk/rules). The CLI guards the starred ones.

1. ★ Tree parent submitted directly under countOnlyLeaves → 0 rows, no error.
   Guard: encode_params expands parents to leaves.
2. ★ Guest tokens: uncredentialed requests mint a fresh guest per request —
   results belong to nobody and /users paths 401. Guard: whoami / user_id()
   refuse guests.
3. ★ Duplicate Authorization cookie pairs: Tomcat honors the first. Guard: the
   client sends exactly one.
4. ★ Retrying a committed create after a proxy 502 duplicates objects. Guard:
   creates are single-attempt.
5. ★ estimatedSize/count 0 vs absent vs -1: absent/-1 means "nobody measured",
   not "empty". Guard: shaping reports "unmeasured", never fabricates 0.
6. ★ input-step params given real values are rejected or mis-wired. Guard:
   always "".
7. Hidden params are still validated (isVisible is presentation-only) — they
   are auto-submitted with defaults; if a hidden default is invalid the WDK
   422 names it.
8. Multi-pick enumeration: one representative value ≠ the covered set. List
   every value you mean. A vocabulary + free-text pair covering the same
   concept is ORed by the search — pass "N/A" to the half you don't use (the
   sheet default usually does this).
9. initialDisplayValue is not a promise: a default may be stale; a 0 count
   with defaults means check the params, not the biology.
10. `isValid: true` at validation level NONE means "nobody checked", not
    "valid". Only the level the response names was checked.
11. Single-pick param + JSON array value = HTTP 500 (not 422). Send a scalar.
12. Number-ish params reject thousands separators ("10,000" → 422).
13. One-sided ranges are invalid; supply both bounds (defaults cover the
    other side if you only care about one).
14. A count of 0 after AND-ing many criteria usually means over-narrowing —
    prefer few broad criteria, verify each leaf's count > 0 before combining
    (use `count` per leaf; they're anonymous and parallelizable).
15. ★ Empty initialDisplayValue ('[]') on required multi-pick params: WDK uses
    "[]" as the unselected initial display value for params like `text_search_organism`
    and `organism`, but requires at least 1 selection. `encode_params` enforces
    this locally instead of sending an empty list that triggers HTTP 422.
16. ★ `ai_expression` is an out-of-scope web UI flag, not an expression summary:
    In gene record inspection, you may see an attribute named `ai_expression` ('AI Expression Summary').
    This is merely a UI flag indicating that an AI-powered summary tool exists on the website;
    it is run on-demand by users and cached outside WDK (costing ~USD $1 per gene).
    It is strictly **out of scope** for `wdk.py` and this skill. Do NOT query `ai_expression`,
    do NOT attempt to invoke or scrape it via browser automation, and do NOT write scripts
    trying to find pre-cached AI summaries.
17. ★ Gene expression data lives in paired tables; summarize directly from the ranked catalog:
    Quantitative RNA-seq and microarray data are stored across paired tables (`ExpressionGraphs`
    and `ExpressionGraphsDataTable`). `wdk.py expression <site> <gene_id>` automatically joins them,
    ranks datasets by peak percentile, and provides `top_sample` for each.
    - When asked for a summary of gene expression, summarize directly from this top-ranked catalog:
      datasets with percentiles ≥90–95% immediately reveal the primary tissues, life stages, and
      treatments where the gene is active.
    - Do NOT write custom Python scripts in the scratch directory or attempt to dump all samples
      across dozens of datasets (`all_samples`).
    - Use `--filter <keyword>` (e.g. `--filter gut`) or `--dataset <id>` only when drill-down
      into specific conditions or tissues is explicitly requested.
18. ★ Probing ~/.config or env when `whoami` fails:
    `whoami` is authoritative. It checks both `VEUPATHDB_BEARER_TOKEN` and `~/.config/veupathdb/token`.
    If `whoami` fails, unauthenticated requests are guaranteed to fail with 401. Probing `~/.config`
    or `env` triggers security approval dialogs in desktop environments (Antigravity Desktop) and
    derails the user. Never probe config files or env vars; transition immediately to the onboarding
    questionnaire and run the login command for the user.
19. ★ `fetch-record` and `--tables Sequences` vs `GeneTranscripts`:
    Gene records in VEuPathDB contain `transcript_count`, `exon_count`, `product`, and `location_text`
    directly in their default attributes (`fetch-record <site> <gene_id>`). If structured transcript
    metadata is needed, use `--tables GeneTranscripts`. **Never use `--tables Sequences`** unless raw
    FASTA/DNA sequences are explicitly requested by the user: `Sequences` dumps multi-kilobase
    nucleotide sequences that trigger tool output truncation and context clutter.
20. ★ Never write ad-hoc Python subprocess wrapper scripts to reformat CLI output:
    In desktop agent environments (such as Antigravity Desktop), running arbitrary inline Python
    commands (`python -c "import subprocess..."` or scripts in `scratch/`) triggers interactive
    security approval dialogs. Always consume the structured JSON output directly from the CLI or
    use built-in CLI flags (`--attributes`, `--tables`, `--filter`, `--limit`).
21. ★ ID-list searches (`GeneByLocusTag`) and `input-dataset` parameters:
    WDK searches taking user-provided ID sets (such as `GeneByLocusTag`) use parameter type `input-dataset`.
    In raw WDK REST calls, these expect an uploaded numeric Dataset ID, not gene symbols. `wdk.py`
    automatically handles this: when you pass gene IDs (e.g. `--params '{"ds_gene_ids": "AGAP001234"}'`
    or comma-separated lists), `encode_params` automatically creates the dataset on the fly and
    substitutes the numeric ID. However, for a single gene lookup, `fetch-record <site> <gene_id>`
    is much simpler and faster.
