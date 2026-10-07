#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx"]
# ///
"""VEuPathDB EDA differential expression: explore an RNA-Seq or antibody-array
study, discover and choose a contrast, run DESeq2/limma on the shared EDA
compute cache, and hand the result to wdk.py as a search step.

Run `eda.py --help` for subcommands, `eda.py <sub> --help` for details.
"""
import argparse
import json
import pathlib
import sys


def emit(obj) -> None:
    print(json.dumps(obj, indent=1, ensure_ascii=False))


def fail(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def eda_client_for(site):
    from _client import eda_client, load_token

    return eda_client(site, token=load_token())


def wdk_client_for(site):
    from _client import Client, load_token

    return Client(site, token=load_token())


def resolve_target_arg(site, arg, lookup_search=False):
    """DS_ id or supported search name -> (dataset id, notebook type or None, search or None).

    A DS_ id is matched against the cached search listing only (no network). With
    lookup_search, a miss fetches the listing once (cached 7 days). Several searches on
    one DS_ id: the first by name is used."""
    import difflib

    from _eda import cached_eda_searches, eda_searches

    if arg.startswith("DS_"):
        def find(rows):
            return next((s for s in rows or [] if s["datasetId"] == arg), None)

        hit = find(cached_eda_searches(site))
        if hit is None and lookup_search:
            hit = find(eda_searches(wdk_client_for(site), log=log))
        return arg, (hit or {}).get("notebook"), (hit or {}).get("search")
    if arg.startswith("STUDY_"):
        fail(f"'{arg}' is an EDA-internal study id; eda.py takes the DS_ dataset id")
    searches = eda_searches(wdk_client_for(site), log=log)
    hit = next((s for s in searches if s["search"] == arg), None)
    if hit is None:
        close = difflib.get_close_matches(arg, [s["search"] for s in searches], n=3, cutoff=0.6)
        fail(f"'{arg}' is neither a DS_ id nor a DE/antibody-array search on {site}; did you mean {close}? "
             f"List them with: eda.py de-datasets {site}")
    if not hit["datasetId"]:
        fail(f"{arg} runs on your own uploaded (VDI) datasets: pass that dataset's DS_ id instead")
    return hit["datasetId"], hit["notebook"], hit["search"]


def cmd_de_datasets(args) -> None:
    from _eda import eda_searches

    rows = eda_searches(wdk_client_for(args.site), refresh=args.refresh, log=log)
    if args.json:
        emit(rows)
        return
    print("# datasetId\tmethod\tnotebook\tsearch\tdisplayName")
    for r in rows:
        ds = r["datasetId"] or "(user dataset: pass your DS_ id)"
        print(f"{ds}\t{r['method']}\t{r['notebook']}\t{r['search']}\t{r['displayName']}")


def load_target(args):
    from _eda import resolve_dataset, study_metadata
    from _samples import index_entities, pick_expression_entity

    ds_id, notebook, search = resolve_target_arg(
        args.site, args.dataset, lookup_search=getattr(args, "save", False))
    c = eda_client_for(args.site)
    ds = resolve_dataset(c, ds_id)
    study = study_metadata(c, ds["studyId"], refresh=getattr(args, "refresh", False))
    index = index_entities(study["rootEntity"])
    expr = pick_expression_entity(index, getattr(args, "entity", None))
    return {
        "client": c,
        "site": args.site,
        "dataset": ds,
        "index": index,
        "expr": expr,
        "notebook": notebook,
        "search": search,
    }


def read_filters(args, t):
    """Sample filters for this command (Task 16 adds --filters)."""
    return []


def sample_view(t, filters):
    """Counts for the expression entity's ancestors plus the joined sample table
    (None when an entity is too large for /tabular)."""
    from _eda import entity_count, tabular
    from _samples import MAX_TABULAR_ROWS, ancestors, build_sample_table, variable_meta

    c, sid, index = t["client"], t["dataset"]["studyId"], t["index"]
    chain = ancestors(index, t["expr"]["entityId"])
    meta = variable_meta(index, chain)
    totals = {e: entity_count(c, sid, e, []) for e in chain}
    counts = {e: entity_count(c, sid, e, filters) for e in chain} if filters else dict(totals)
    too_big = [e for e in chain if counts[e] > MAX_TABULAR_ROWS]
    table = None
    if not too_big:
        table = build_sample_table(
            lambda e, ids: tabular(c, sid, e, ids, filters), index, t["expr"]["entityId"], meta
        )
    return {"chain": chain, "meta": meta, "totals": totals, "counts": counts, "table": table, "too_big": too_big}


def study_sections(t, view, filters):
    from _eda import distribution
    from _samples import MAX_TABULAR_ROWS, NUMERIC_TYPES, prune_entity, summarise_from_distribution, summarise_variable

    sections = []
    for eid in reversed(view["chain"]):
        entity = t["index"][eid]["entity"]
        rows = view["table"]["byEntity"][eid] if view["table"] else None
        items = []
        for item in prune_entity(entity):
            if item["kind"] == "category":
                items.append((item, None))
            elif rows is not None:
                items.append((item, summarise_variable(item, [r.get(item["id"]) for r in rows])))
            elif item.get("type") in NUMERIC_TYPES and not item.get("_binSpec"):
                items.append((item, {"kind": "continuous", "n": 0, "missing": 0, "unavailable": "no bin defaults"}))
            else:
                dist = distribution(
                    t["client"], t["dataset"]["studyId"], eid, item["id"], filters,
                    item.get("_binSpec") if item.get("type") in NUMERIC_TYPES else None,
                )
                items.append((item, summarise_from_distribution(item, dist)))
        note = None
        if rows is None:
            note = (
                f"{view['counts'][eid]} records > {MAX_TABULAR_ROWS}: per-variable /distribution "
                "summaries, no joint sample table (contrasts and pca need it: narrow with --filters)"
            )
        sections.append(
            {
                "entityId": eid,
                "displayName": entity.get("displayName", eid),
                "records": view["counts"][eid],
                "total": view["totals"][eid],
                "items": items,
                "note": note,
            }
        )
    return sections


def other_entities(t, view, filters):
    from _eda import entity_count

    skip = set(view["chain"]) | {t["expr"]["entityId"]}
    return [
        {
            "entityId": eid,
            "displayName": node["entity"].get("displayName", eid),
            "records": entity_count(t["client"], t["dataset"]["studyId"], eid, filters),
        }
        for eid, node in t["index"].items()
        if eid not in skip
    ]


def contrast_setup(args, t, filters):
    """Shared by contrasts/de/de-spec: sample view, value variable, method, notes."""
    from _contrasts import choose_method, choose_value_var
    from _eda import EdaError
    from _samples import MAX_TABULAR_ROWS

    view = sample_view(t, filters)
    if view["table"] is None:
        raise EdaError(
            f"{', '.join(view['too_big'])} has more than {MAX_TABULAR_ROWS} records; contrasts need "
            "the joint sample table. Narrow it with --filters."
        )
    value_var, vnote = choose_value_var(t["expr"], getattr(args, "value_var", None))
    method, mnote = choose_method(t["notebook"], value_var, getattr(args, "method", "auto"))
    return view, value_var, method, [n for n in (vnote, mnote) if n]


def _only_vars(args):
    return set(args.vars.split(",")) if getattr(args, "vars", None) else None


def cmd_contrasts(args) -> None:
    import _contrasts
    from _contrasts import PLUGIN_DE, compute_body, de_config, enumerate_contrasts, job_id, render_contrasts
    from _eda import compute_status

    t = load_target(args)
    filters = read_filters(args, t)
    view, value_var, method, notes = contrast_setup(args, t, filters)
    result = enumerate_contrasts(view["table"]["rows"], view["meta"], filters, _only_vars(args))
    for cand in result["candidates"]:
        cfg = de_config(t["expr"]["entityId"], value_var, cand["comparator"], cand["groupA"], cand["groupB"], method)
        body = compute_body(t["dataset"]["studyId"], cfg, cand["filters"])
        if cand["index"] <= _contrasts.MAX_CACHE_CHECKS:
            st = compute_status(t["client"], PLUGIN_DE, body, start=False)
            cand["cache"] = {"status": st["status"], "jobId": st["jobID"]}
        else:
            cand["cache"] = {"status": "not checked", "jobId": job_id(PLUGIN_DE, body)}
    out = {"datasetId": t["dataset"]["datasetId"], "valueVariable": value_var, "method": method, "notes": notes, **result}
    if args.json:
        emit(out)
    else:
        print("\n".join(render_contrasts(out)))


def json_arg(raw, flag, expected):
    """Inline JSON (starts with { or [) or a JSON file path (an optional leading @, as in
    wdk.py). Inline is the default for small objects, so no glue files are needed."""
    from _eda import EdaError

    text = raw.strip()
    if text[:1] in ("{", "["):
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise EdaError(f"{flag}: inline JSON is not valid: {e}") from None
    path = pathlib.Path(text.removeprefix("@")).expanduser()
    if not path.is_file():
        raise EdaError(f"{flag} {raw!r} is not {expected} (file not found: {path})")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise EdaError(f"{flag} file {path} is not valid JSON: {e}") from None


def resolve_contrast(args, t, filters, view):
    from _contrasts import enumerate_contrasts, load_contrast
    from _eda import EdaError
    from _samples import all_var_entities

    spec = args.contrast
    if spec.isdigit():
        out = enumerate_contrasts(view["table"]["rows"], view["meta"], filters, _only_vars(args))
        cands = out["candidates"]
        hit = next((c for c in cands if c["index"] == int(spec)), None)
        if hit is None:
            more = " (the list is capped: narrow it with --vars)" if out["truncated"] else ""
            raise EdaError(
                f"--contrast {spec}: no such candidate (1..{len(cands)}){more}; re-run 'eda.py contrasts' "
                "with the same --filters/--vars/--value-var"
            )
        return hit
    obj = json_arg(spec, "--contrast", "a candidate number, inline JSON or a contrast file")
    return load_contrast(obj, view["meta"], all_var_entities(t["index"]), view["chain"], filters)


def contrast_counts(t, contrast, base_filters, view):
    """Samples per group under the contrast's own filters (strata included)."""
    from _contrasts import canonical_filters, samples_in_group
    from _eda import EdaError

    rows = view["table"]["rows"]
    if contrast["filters"] != canonical_filters(base_filters):
        sub = sample_view(t, contrast["filters"])["table"]
        rows = sub["rows"] if sub else []
    vid = contrast["comparator"]["variableId"]
    a = samples_in_group(rows, vid, contrast["groupA"])
    b = samples_in_group(rows, vid, contrast["groupB"])
    both = sorted(set(a) & set(b))
    if both:
        raise EdaError(f"samples fall in both groups: {both[:5]}")
    return len(a), len(b)


def prepare_de(args):
    """Everything de and de-spec share, so de-spec's config is exactly what de hashed."""
    from _contrasts import compute_body, de_config, replicate_check

    t = load_target(args)
    filters = read_filters(args, t)
    view, value_var, method, notes = contrast_setup(args, t, filters)
    contrast = resolve_contrast(args, t, filters, view)
    n_a, n_b = contrast_counts(t, contrast, filters, view)
    rnote = replicate_check(n_a, n_b)
    if rnote:
        notes.append(rnote)
    cfg = de_config(t["expr"]["entityId"], value_var, contrast["comparator"], contrast["groupA"], contrast["groupB"], method)
    body = compute_body(t["dataset"]["studyId"], cfg, contrast["filters"])
    return {"t": t, "contrast": contrast, "nA": n_a, "nB": n_b, "valueVar": value_var,
            "method": method, "config": cfg, "body": body, "notes": notes}


def de_context(p, thresholds):
    c, ds = p["contrast"], p["t"]["dataset"]
    fc, pv, direction = thresholds
    a = [g["label"] for g in c["groupA"]]
    b = [g["label"] for g in c["groupB"]]
    return {
        "study": ds["displayName"],
        "description": ds["description"],
        "comparator": {"variable": c["comparator"]["displayName"], "variableId": c["comparator"]["variableId"],
                       "entityId": c["comparator"]["entityId"]},
        "groupA": {"labels": a, "n": p["nA"], "role": "reference"},
        "groupB": {"labels": b, "n": p["nB"], "role": "comparison"},
        "orientation": f"positive effectSize = higher in groupB ({'+'.join(b)}) than groupA ({'+'.join(a)}); "
                       "unshrunk log2 fold change",
        "method": p["method"],
        "valueVariable": p["valueVar"],
        "filters": c["filters"],
        "thresholds": {"effectSize": fc, "pValue": pv, "direction": direction,
                       "pValueType": "raw (as the website volcano plot and the WDK step)"},
        "notes": p["notes"] + list(c.get("notes") or []),
    }


def mirror_body(p):
    """The same contrast with groupA and groupB swapped: a different job, same statistics
    with effectSize negated (see _de.negate_effects)."""
    from _contrasts import compute_body, de_config

    c = p["contrast"]
    cfg = de_config(p["t"]["expr"]["entityId"], p["valueVar"], c["comparator"], c["groupB"], c["groupA"], p["method"])
    return compute_body(p["t"]["dataset"]["studyId"], cfg, c["filters"])


def _next_hint(p, args):
    import shlex

    return (
        f"next (same --filters/--vars/--value-var): eda.py de-spec {args.site} {args.dataset} "
        f"--contrast {shlex.quote(args.contrast)} --thresholds {args.thresholds} --save, then use the "
        "printed \"leaf\" in wdk.py create-strategy --spec (no file of your own needed)"
    )


def cmd_de(args) -> None:
    from _client import WDKError
    from _contrasts import PLUGIN_DE
    from _de import de_json, de_table, gene_rows, negate_effects, parse_thresholds, render_de, summarise, table_tsv
    from _eda import EdaError, compute_status, delete_job, volcano, wait_for_job

    thresholds = parse_thresholds(args.thresholds)
    p = prepare_de(args)
    t, body = p["t"], p["body"]
    c = t["client"]
    if args.no_wait:
        st = compute_status(c, PLUGIN_DE, body, start=True)
        emit({"jobId": st["jobID"], "status": st["status"],
              "next": "re-run without --no-wait to fetch results (the job keeps running server-side)"})
        return
    mirror = None
    if not args.no_mirror:
        st = compute_status(c, PLUGIN_DE, body, start=False)
        if st["status"] == "no-such-job":
            mbody = mirror_body(p)
            mst = compute_status(c, PLUGIN_DE, mbody, start=False)
            if mst["status"] == "complete":
                mirror = {"jobId": mst["jobID"], "negated": True}
    if mirror:
        stats = negate_effects(volcano(c, mbody)["statistics"])
        p["notes"].append(
            f"statistics reused from the cached mirror job {mirror['jobId']} (groups swapped), effect sizes "
            "negated; p-values are unchanged by the swap. The WDK step for this orientation is not cached: "
            "creating it starts its own job (the first answer is HTTP 202)"
        )
    else:
        st = wait_for_job(c, PLUGIN_DE, body, timeout_s=args.timeout, log=log)
        if st["status"] in ("failed", "expired") and args.retry:
            if st["status"] == "failed":
                try:
                    delete_job(c, st["jobID"])
                except WDKError as e:
                    log(f"could not delete failed job {st['jobID']}: {e}")
            st = wait_for_job(c, PLUGIN_DE, body, timeout_s=args.timeout, log=log)
        if st["status"] != "complete":
            hint = ""
            if st["status"] == "failed":
                hint = (" A job that fails quickly usually means a bad config (e.g. identifier and value "
                        "variables on different entities).")
            raise EdaError(f"job {st['jobID']} is {st['status']}.{hint} --retry resubmits it.")
        stats = volcano(c, body)["statistics"]
    table = de_table(stats)
    summary = summarise(stats, thresholds, top_n=args.top)
    context = de_context(p, thresholds)
    provenance = {"site": t["site"], "datasetId": t["dataset"]["datasetId"], "studyId": t["dataset"]["studyId"],
                  "plugin": PLUGIN_DE, "jobId": st["jobID"], "statisticsFrom": mirror, "search": t["search"]}
    genes = [g.strip() for g in args.genes.split(",") if g.strip()] if args.genes else []
    if args.tsv:
        pathlib.Path(args.tsv).write_text(table_tsv(table), encoding="utf-8")
        log(f"wrote {len(table)} rows to {args.tsv}")
    if args.json:
        extra = list(genes)
        if args.rows == "passing":
            extra += summary["passing_raw_genes"]
        elif args.rows == "all":
            extra += [r["gene"] for r in table]
        emit(de_json(context, provenance, summary, table, extra))
        return
    lines = render_de(context, provenance, summary, t["expr"]["geneCount"],
                      gene_rows(table, genes) if genes else None, _next_hint(p, args))
    print("\n".join(lines))


def cmd_de_spec(args) -> None:
    from _client import stash_json
    from _contrasts import PLUGIN_DE, job_id, pca_config
    from _de import build_spec, parse_thresholds, validate_spec, wdk_params

    thresholds = parse_thresholds(args.thresholds)
    p = prepare_de(args)
    t, c = p["t"], p["contrast"]
    ds = t["dataset"]
    name = (
        f"{ds['shortDisplayName'] or ds['displayName']}: "
        f"{'+'.join(g['label'] for g in c['groupB'])} vs {'+'.join(g['label'] for g in c['groupA'])}"
    )[:200]
    spec = build_spec(ds["datasetId"], name, c["filters"], p["config"],
                      pca_config(t["expr"]["entityId"], p["valueVar"]), thresholds)
    validate_spec(spec, ds["datasetId"])
    log(f"DE job id {job_id(PLUGIN_DE, p['body'])} (same body as 'eda.py de'; run de first so the WDK step answers at once)")
    if args.save:
        path = str(stash_json("params", wdk_params(spec)))
        out = {"paramsFile": path, "leaf": {"search": t["search"], "params": "@" + path}}
        if not t["search"]:
            out["note"] = "no search name known for this dataset: find it with 'eda.py de-datasets SITE'"
        emit(out)
        return
    emit(wdk_params(spec) if args.format == "params" else spec)


def cmd_study(args) -> None:
    from _samples import render_study, study_json

    t = load_target(args)
    filters = read_filters(args, t)
    view = sample_view(t, filters)
    sections = study_sections(t, view, filters)
    others = other_entities(t, view, filters)
    if args.json:
        emit(study_json(t["dataset"], t["expr"], sections, others, view["table"], filters))
    else:
        print("\n".join(render_study(t["dataset"], t["expr"], sections, others)))


def _target_args(sp):
    sp.add_argument("site")
    sp.add_argument("dataset", help="DS_ dataset id, or a DE/antibody-array search name (see de-datasets)")
    sp.add_argument("--entity", help="expression entity id, when the study has several")
    sp.add_argument("--refresh", action="store_true", help="bypass the 7-day study metadata cache")


def _contrast_args(sp):
    sp.add_argument("--value-var", help="expression value variable (default: unstranded counts, else sense, else intensity)")
    sp.add_argument("--method", default="auto", choices=["auto", "DESeq", "limma"],
                    help="auto = the website's method for this search family")
    sp.add_argument("--vars", help="comma-separated comparator variable ids to consider")


def _de_args(sp):
    from _de import DEFAULT_THRESHOLDS

    sp.add_argument("--contrast", required=True,
                    help="candidate number from 'contrasts', inline contrast JSON, or a contrast JSON file")
    sp.add_argument("--thresholds", default=DEFAULT_THRESHOLDS,
                    help="FC,P[,upAndDown|upOnly|downOnly]: |log2FC| >= FC and raw p <= P (website defaults)")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="eda.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("study", help="pruned overview of a study's samples and annotation")
    _target_args(sp)
    sp.add_argument("--json", action="store_true", help="pruned structure plus the sample table")
    sp.set_defaults(func=cmd_study)

    sp = sub.add_parser("contrasts", help="canonical candidate contrasts with replicate counts and cache status")
    _target_args(sp)
    _contrast_args(sp)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_contrasts)

    sp = sub.add_parser("de", help="run (or reuse) DESeq2/limma for one contrast and summarise the result")
    _target_args(sp)
    _contrast_args(sp)
    _de_args(sp)
    sp.add_argument("--genes", help="comma-separated gene ids to report (absent = not tested)")
    sp.add_argument("--rows", choices=["none", "passing", "all"], default="none",
                    help="--json: which gene rows to include besides the top lists")
    sp.add_argument("--top", type=int, default=10, help="top up/down genes by effect size among padj passers")
    sp.add_argument("--tsv", help="write the full table (gene, effectSize, pValue, adjustedPValue)")
    sp.add_argument("--json", action="store_true", help="identity/context/provenance/rows JSON")
    sp.add_argument("--no-wait", action="store_true", help="start the job and report its status only")
    sp.add_argument("--retry", action="store_true", help="resubmit a failed or expired job")
    sp.add_argument("--timeout", type=int, default=900, help="seconds to wait for the job (default 900)")
    sp.add_argument("--no-mirror", action="store_true",
                    help="never reuse the cached swapped-groups job; always run this orientation")
    sp.set_defaults(func=cmd_de)

    sp = sub.add_parser("de-spec", help="print the eda_analysis_spec (or WDK params) for a contrast")
    _target_args(sp)
    _contrast_args(sp)
    _de_args(sp)
    sp.add_argument("--format", choices=["spec", "params"], default="spec",
                    help="spec = the analysis JSON; params = {eda_dataset_id, eda_analysis_spec} for wdk.py --params @file")
    sp.add_argument("--save", action="store_true",
                    help="write the WDK params to the skill cache (content-addressed) and print the path and a "
                         "ready-made strategy leaf; nothing is written to the working directory")
    sp.set_defaults(func=cmd_de_spec)

    sp = sub.add_parser("de-datasets", help="DE and antibody-array searches with their DS_ ids and methods")
    sp.add_argument("site")
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--refresh", action="store_true", help="re-read the WDK catalog and search details")
    sp.set_defaults(func=cmd_de_datasets)
    return p


def main(argv=None) -> None:
    from _client import WDKError
    from _eda import EdaError
    from _sites import UnknownSiteError

    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except (UnknownSiteError, WDKError, EdaError) as e:
        fail(str(e))


if __name__ == "__main__":
    main()
