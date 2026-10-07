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


def resolve_target_arg(site, arg):
    """DS_ id -> (dataset id, notebook type or None, search name or None)."""
    if not arg.startswith("DS_"):
        fail(f"'{arg}' is not a DS_ dataset id (STUDY_ ids are EDA-internal; eda.py takes the DS_ id)")
    return arg, None, None


def load_target(args):
    from _eda import resolve_dataset, study_metadata
    from _samples import index_entities, pick_expression_entity

    ds_id, notebook, search = resolve_target_arg(args.site, args.dataset)
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
    sp.add_argument("dataset", help="DS_ dataset id")
    sp.add_argument("--entity", help="expression entity id, when the study has several")
    sp.add_argument("--refresh", action="store_true", help="bypass the 7-day study metadata cache")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="eda.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("study", help="pruned overview of a study's samples and annotation")
    _target_args(sp)
    sp.add_argument("--json", action="store_true", help="pruned structure plus the sample table")
    sp.set_defaults(func=cmd_study)

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
