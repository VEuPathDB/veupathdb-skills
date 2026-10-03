# Gold-standard test registry

Gold standards captured live on 2026-08-27. Counts drift with VEuPathDB data releases (~4/year): a `range` failure within ~20% of gold means re-capture, not code bug. Any other failure is a regression.

Live services drift with data releases; each case states its tolerance:
`exact` | `range` (± stated) | `fields-present`.
Run all: `uv run --with pytest --with httpx python -m pytest tests -q`

| ID | Command / pytest node | Expectation | Tolerance | Gold (captured) | Date |
|---|---|---|---|---|---|
| AUTH-1 | `wdk.py whoami plasmodb` / test_client.py::test_live_whoami | numeric user_id, not guest | fields-present | user_id=578013513 | 2026-08-27 |
| AUTH-2 | test_client.py::test_guest_token_is_refused | guest refusal names registration | exact (offline) | message contains "register" | 2026-08-27 |
| CAT-1 | `wdk.py record-types plasmodb` | contains transcript, organism, dataset | fields-present | 24 record types | 2026-08-27 |
| CAT-2 | `wdk.py catalog plasmodb` | header + one TSV line per non-boolean search | range ±20% | 495 lines | 2026-08-27 |
| CAT-3 | `wdk.py catalog vectorbase` | as CAT-2 | range ±20% | 995 lines | 2026-08-27 |
| CAT-4 | `wdk.py catalog toxodb` | as CAT-2 | range ±20% | 385 lines | 2026-08-27 |
| FIND-1 | `wdk.py find-searches plasmodb "GO term"` | GenesByGoTerm in top 5 | fields-present | rank=1 | 2026-08-27 |
| INS-1 | `wdk.py inspect-search plasmodb GenesByMolecularWeight` | 3 visible params; organism tree; min default 10000 | exact (offline fixture) | see tests/fixtures/mw.json | 2026-08-27 |
| INS-2 | `wdk.py inspect-search plasmodb GenesByGoTerm --query kinase` | go_typeahead shortlisted with note (5992 total) | range: total >5000 | 5992 | 2026-08-27 |
| INS-3 | `wdk.py inspect-search plasmodb GenesByMolecularWieght` | did-you-mean GenesByMolecularWeight, exit 1 | exact | — | 2026-08-27 |
| INS-4 | `wdk.py inspect-record-type vectorbase gene --query exon` / test_record.py::test_live_inspect_record_type_gene_vectorbase | primary_key has source_id/project_id; attributes has exon_count; tables has GeneTranscripts | fields-present | PK=['source_id', 'project_id'] | 2026-09-10 |
| INS-5 | `wdk.py inspect-record-type vectorbase genee` | did-you-mean gene, exit 1 | exact | error: unknown record type 'genee' | 2026-09-10 |
| OPT-1 | `wdk.py param-options plasmodb GenesByGoTerm go_typeahead --query kinase` | filtered options + context_note naming go_term_slim | fields-present | shown=155 | 2026-08-27 |
| OPT-2 | `wdk.py param-options plasmodb GenesByGoTerm go_typahead` | did_you_mean includes go_typeahead | exact | — | 2026-08-27 |
| CNT-1 | `wdk.py count plasmodb GenesByMolecularWeight --params '{"organism": ["Plasmodium falciparum 3D7"]}'` | 2365 genes | range 1800–3000 | 2365 | 2026-08-27 |
| CNT-2 | `wdk.py count plasmodb GenesByMolecularWeight --params '{"organism": ["Plasmodium"]}'` | > CNT-1 count | range | 157941 | 2026-08-27 |
| PRV-1 | `wdk.py preview plasmodb GenesByMolecularWeight --params '{"organism": ["Plasmodium falciparum 3D7"]}' --limit 3` | 3 records with gene_source_id ids | fields-present | first id PF3D7_0100200 | 2026-08-27 |
| STR-1 | test_strategy.py::test_live_two_leaf_intersect / `wdk.py create-strategy plasmodb --spec '{"combine": {"operator": "INTERSECT", "left": {"leaf": {"search": "GenesByMolecularWeight", "params": {"organism": ["Plasmodium falciparum 3D7"], "min_molecular_weight": "10000", "max_molecular_weight": "50000"}}}, "right": {"leaf": {"search": "GenesByMolecularWeight", "params": {"organism": ["Plasmodium falciparum 3D7"], "min_molecular_weight": "40000", "max_molecular_weight": "100000"}}}}}'` | 3 steps; root ≤ min(leaves); root > 0; url valid | range | root=521, leaves=[2365, 1842] | 2026-08-27 |
| STR-2 | `wdk.py strategy plasmodb <strategy_id>` | same shape as create output | fields-present | — | 2026-08-27 |
| STR-3 | `wdk.py delete-strategy plasmodb <strategy_id>` (without `--yes`) | refuses without `--yes`, exit 1 | exact | error: refusing to delete without --yes | 2026-08-27 |
| CNT-3 | `wdk.py count vectorbase GenesByMolecularWeight --params '{"organism": ["Anopheles gambiae PEST"]}'` / test_reports.py::test_live_count_vectorbase | >0, within range | range ±20% of gold | 6755 | 2026-08-27 |
| RES-1 | `wdk.py results plasmodb --step <step_id> --limit 2` / test_results.py::test_live_step_records | 2 records with gene ids | fields-present | — | 2026-08-27 |
| DL-1 | `wdk.py download-url plasmodb --step <step_id>` / test_results.py::test_live_download_url | URL containing /temporary-results/ | fields-present | report=attributesTabular | 2026-08-27 |
| REC-1 | `wdk.py fetch-record vectorbase AGAP001212 --tables GeneTranscripts` / test_record.py::test_live_fetch_gene_record_vectorbase | name=PGRPLB, exon_count=3, GeneTranscripts table | fields-present | name=PGRPLB, exon_count=3 | 2026-09-10 |
| REC-2 | `wdk.py fetch-record vectorbase AGAP006348 --tables Orthologs --filter albimanus` / test_record.py::test_live_fetch_record_filter_tables | 2 albimanus rows, clustalInput/sort_key stripped | fields-present | 2 rows (AALB20_030456, AALB005865) | 2026-09-10 |
| E2E-1 | test_strategy.py::test_live_vectorbase_strategy_lifecycle / `wdk.py create-strategy vectorbase --spec '{"combine": {"operator": "INTERSECT", "left": {"leaf": {"search": "GenesByMolecularWeight", "params": {"organism": ["Anopheles gambiae PEST"], "min_molecular_weight": "10000", "max_molecular_weight": "50000"}}}, "right": {"leaf": {"search": "GenesByMolecularWeight", "params": {"organism": ["Anopheles gambiae PEST"], "min_molecular_weight": "40000", "max_molecular_weight": "100000"}}}}}'` | 3 steps; root ≤ min(leaves); root > 0; url valid | range | root=1657, leaves=[6755, 5676] | 2026-09-10 |
| CAT-5 | test_catalog.py::test_live_catalog_excludes_eda_searches / `wdk.py find-searches vectorbase DESeq` | no eda_ searches in default catalog; unavailable note on direct inspect | exact | 0 eda_ in default; >100 when disabled | 2026-09-10 |
| CNT-4 | `wdk.py count vectorbase GenesByMicroarrayagamPEST_microarrayExpression_GSE8822_bloodmeal_response_RSRC --params '{"profileset_generic": "bloodmeal_time_series", "samples_fc_ref_generic": ["non-blood-fed"], "samples_fc_comp_generic": ["blood-fed 3h"]}'` / test_reports.py::test_live_count_dependent_params | >0, within range (resolves dependent vocabularies) | range ±20% of gold | 1753 | 2026-09-10 |
| STR-4 | test_strategy.py::test_live_strategy_with_dependent_params | 1 step, estimated_size ~1753, url valid | range | 1753 | 2026-09-10 |
| PROMPT-1 | "How many exons does the longest transcript of Anopheles gambiae gene PGPRLB have?" | VectorBase, gene AGAP001212, longest transcript exon count: 3 | exact | site=VectorBase, gene=AGAP001212, exon_count=3 | 2026-09-10 |
| PROMPT-2 | "What is the Anopheles albimanus ortholog of Anopheles gambiae LRIM1 (AGAP006348)?" | VectorBase, gene AGAP006348, Orthologs table filtered to Anopheles albimanus (AALB20_030456 / AALB005865) | exact | site=VectorBase, gene=AGAP006348, orthologs=[AALB20_030456, AALB005865] | 2026-09-10 |
| INS-6 | `wdk.py inspect-record-type vectorbase transcript --filter product --name-only --exclude graph` / test_record.py::test_live_inspect_record_type_name_only_and_exclude | returns only gene_product and transcript_product (name-only matching + graph exclusion) | fields-present | matching_attributes=2 | 2026-09-11 |
| INS-7 | `wdk.py inspect-record-type vectorbase transcript --exclude pan_` / test_record.py::test_live_inspect_record_type_name_only_and_exclude | excludes all Protocol Application Node columns | fields-present | 0 pan_ attributes in output | 2026-09-11 |
| RES-2 | `wdk.py results plasmodb --step <step_id> --limit 2` / test_results.py::test_live_step_records_with_default_attributes | returns records populated with search's defaultAttributes without passing --attributes | fields-present | attributes contains primary_key, gene_product | 2026-09-11 |
| AUTH-3 | `wdk.py login plasmodb --token <KEY>` & `wdk.py logout` / test_client.py::test_cli_login_token_and_logout | stores token in ~/.config/veupathdb/token (mode 0600); deletes on logout | exact (offline) | mode 0600 | 2026-09-11 |
| AUTH-4 | `wdk.py whoami <site>` (unauthenticated) / test_client.py::test_cli_whoami_unauthenticated | actionable onboarding error message with site-specific login/profile/registration links | fields-present | contains login, profile, registration URLs | 2026-09-11 |
| AUTH-5 | `wdk.py login plasmodb --token -` (stdin) / test_client.py::test_cli_login_token_from_stdin | verifies and stores token piped from standard input | exact (offline) | mode 0600 | 2026-09-12 |
| AUTH-6 | `wdk.py login plasmodb --token-file <PATH>` / test_client.py::test_cli_login_token_from_file | reads token from file, verifies and stores in config (mode 0600) | exact (offline) | mode 0600 | 2026-09-14 |
| SITE-1 | `wdk.py detect-site "<query>"` / test_client.py::test_cli_detect_site & test_sites.py::test_detect_site_from_queries | maps organism/pathogen/vector keywords to community site (toxodb, vectorbase, etc.) with veupathdb fallback | exact | community site id + URLs | 2026-09-11 |
| ENC-1 | `encode_params(_mw(), {})` & `encode_params(_mw(), {"organism": []})` / test_encode.py::test_missing_required_multipick_raises_param_error | catches unselected/empty required multi-pick parameters locally; instructs param-options | exact (offline) | ParamError naming parameter and options | 2026-09-11 |
| ENC-2 | `encode_params(_dataset_search(), {"ds_gene_ids": "AGAP001234"})` / test_encode.py | handles `input-dataset` parameters; auto-uploads ID sets via client into WDK datasets; suggests `fetch-record` if client missing | exact | dataset ID substituted / clear error | 2026-09-14 |
| DATASET-1 | `Client.create_id_dataset(["AGAP001234"])` / test_client.py::test_create_id_dataset_unit & test_live_create_id_dataset | uploads ID lists to `POST /users/current/datasets` and returns integer dataset ID | exact | integer dataset ID > 0 | 2026-09-14 |
| EXPR-1 | `wdk.py expression vectorbase AGAP009221 --dataset DS_46d69d95d1` / test_expression.py | joins ExpressionGraphs and ExpressionGraphsDataTable; ranks samples descending by percentile; supports summary and keyword filters | fields-present | total_datasets=40, top_sample="carcass: male (val: 9.23, pct: 97.1%)" | 2026-09-11 |
| PROMPT-3 | "Where is Anopheles gambiae SRPN5 (AGAP009221) expressed across body parts and tissues?" | VectorBase, `wdk.py expression vectorbase AGAP009221 --filter body` or `--dataset DS_46d69d95d1` | exact | site=VectorBase, top_tissues=[carcass male (97.1%), head male (97.0%), whole body male (96.0%), maxillary palps female (97.8%)] | 2026-09-11 |




