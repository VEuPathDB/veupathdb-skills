#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx"]
# ///
"""VEuPathDB WDK CLI — build search strategies from the command line.

Run `wdk.py --help` for subcommands, `wdk.py <sub> --help` for details.
"""
import argparse
import getpass
import json
import pathlib
import sys

from _sites import (
    SITES,
    UnknownSiteError,
    detect_site,
    profile_url,
    project_id,
    registration_url,
    service_url,
    strategy_url,
)


def emit(obj) -> None:
    print(json.dumps(obj, indent=1, ensure_ascii=False))


def fail(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def client(site_id):
    from _client import Client, load_token

    return Client(site_id, token=load_token())


def cmd_sites(args) -> None:
    emit(
        {
            sid: {"service": cfg["base_url"], "project": cfg["project_id"]}
            for sid, cfg in sorted(SITES.items())
        }
    )


def cmd_whoami(args) -> None:
    from _client import load_token

    tok = load_token()
    if not tok:
        proj = project_id(args.site)
        prof = profile_url(args.site)
        reg = registration_url(args.site)
        fail(
            f"not logged in. VEuPathDB authentication is required.\n\n"
            f"To log in with your browser API key:\n"
            f"  1. Log in at: {prof}\n"
            f"  2. Copy your API key from the 'Service Access' tab\n"
            f"  3. Save to a file: echo '<KEY>' > /tmp/{args.site}-key\n"
            f"     Run:           uv run scripts/wdk.py login {args.site} --token-file /tmp/{args.site}-key\n"
            f"     (Or directly:  uv run scripts/wdk.py login {args.site} --token <KEY>)\n\n"
            f"Need an account? Register at: {reg}"
        )
    c = client(args.site)
    me = c.get("/users/current")
    if me.get("isGuest"):
        fail(
            "token identifies a GUEST user; register at the site and supply a "
            "registered-user bearer token"
        )
    emit({"site": args.site, "user_id": me["id"], "email": me.get("email")})


def cmd_login(args) -> None:
    from _client import (
        save_token,
        token_path,
        verify_token,
    )

    token_file_arg = getattr(args, "token_file", None)
    site_id = (args.site or "").strip().lower()
    if not site_id:
        if args.token or token_file_arg:
            site_id = "veupathdb"
        elif sys.stdin.isatty():
            try:
                choice_site = input("VEuPathDB site [veupathdb]: ").strip().lower()
                site_id = choice_site if choice_site else "veupathdb"
            except (KeyboardInterrupt, EOFError):
                print()
                sys.exit(1)
        else:
            site_id = "veupathdb"

    if site_id not in SITES:
        raise UnknownSiteError(
            f"unknown site '{site_id}'; valid: {', '.join(sorted(SITES))}"
        )

    # 1. Direct token provided via flag or file
    tok = None
    if token_file_arg:
        p = pathlib.Path(token_file_arg).expanduser()
        if not p.is_file():
            fail(f"token file not found: {p}")
        tok = p.read_text(encoding="utf-8").strip()
    elif args.token:
        raw = args.token.strip()
        if raw.startswith("@"):
            p = pathlib.Path(raw[1:]).expanduser()
            if not p.is_file():
                fail(f"token file not found: {p}")
            tok = p.read_text(encoding="utf-8").strip()
        elif raw == "-":
            tok = sys.stdin.read().strip()
        elif pathlib.Path(raw).expanduser().is_file():
            tok = pathlib.Path(raw).expanduser().read_text(encoding="utf-8").strip()
        else:
            tok = raw

    if tok:
        print(f"Verifying token against {site_id}...", file=sys.stderr)
        try:
            user = verify_token(site_id, tok)
        except Exception as e:
            fail(f"failed to verify token: {e}")
        p = save_token(tok)
        email = user.get("email") or "unknown"
        uid = user.get("id") or "unknown"
        print(f"✓ Authenticated: {email} (id={uid}) on {site_id}")
        print(f"✓ Saved token to {p} (mode 0600)")
        return

    # 2. Interactive wizard
    if not sys.stdin.isatty():
        fail("interactive login requires a TTY. Use --token-file <PATH> or --token <KEY> (or --token -).")

    proj = project_id(site_id)
    prof = profile_url(site_id)
    reg = registration_url(site_id)

    print()
    print(f"VEuPathDB Authentication ({proj})")
    print("─" * 60)
    print("Choose how you would like to authenticate:")
    print("  [1] Paste API key from browser (User menu -> My Account -> Service Access)")
    print(f"  [2] Read API key from file (e.g. /tmp/{site_id}-key)")
    print("  [3] Register a new account (opens registration link)")
    print("  [q] Quit")
    print()

    try:
        choice = input("Choice [1]: ").strip()
    except (KeyboardInterrupt, EOFError):
        print()
        sys.exit(1)

    if choice in ("q", "quit", "exit"):
        sys.exit(0)
    elif choice == "2":
        print()
        try:
            path_str = input(f"Path to token file [e.g. /tmp/{site_id}-key]: ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            sys.exit(1)
        if not path_str:
            fail("no token file provided")
        p = pathlib.Path(path_str).expanduser()
        if not p.is_file():
            fail(f"token file not found: {p}")
        tok = p.read_text(encoding="utf-8").strip()
        if not tok:
            fail("token file is empty")
        print(f"Verifying token against {site_id}...", file=sys.stderr)
        try:
            user = verify_token(site_id, tok)
        except Exception as e:
            fail(f"invalid API key: {e}")
        saved = save_token(tok)
        email = user.get("email") or "unknown"
        uid = user.get("id") or "unknown"
        print(f"✓ Authenticated: {email} (id={uid}) on {site_id}")
        print(f"✓ Saved token to {saved} (mode 0600)")
    elif choice == "3":
        print()
        print(f"Register for free at: {reg}")
        print("After registering, log in to your profile, copy your API key, and run 'wdk.py login --token <KEY>' or '--token-file <PATH>'.")
        sys.exit(0)
    else:  # default option 1
        print()
        print(f"Open your profile: {prof}")
        print("Copy your API key from the 'Service Access' tab.")
        try:
            tok = getpass.getpass("Paste API key (typing hidden): ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            sys.exit(1)
        if not tok:
            fail("no API key provided")
        print(f"Verifying token against {site_id}...", file=sys.stderr)
        try:
            user = verify_token(site_id, tok)
        except Exception as e:
            fail(f"invalid API key: {e}")
        p = save_token(tok)
        email = user.get("email") or "unknown"
        uid = user.get("id") or "unknown"
        print(f"✓ Authenticated: {email} (id={uid}) on {site_id}")
        print(f"✓ Saved token to {p} (mode 0600)")


def cmd_logout(args) -> None:
    from _client import delete_token, token_path

    p = token_path()
    if delete_token():
        print(f"✓ Logged out. Removed {p}")
    else:
        print(f"No stored token found at {p}")


def cmd_detect_site(args) -> None:
    detected = detect_site(args.query)
    emit(
        {
            "query": args.query,
            "site": detected,
            "project": project_id(detected),
            "service_url": service_url(detected),
            "profile_url": profile_url(detected),
            "registration_url": registration_url(detected),
        }
    )



def cmd_record_types(args) -> None:
    emit(client(args.site).get("/record-types"))


def _parse_excluded_prefixes(arg):
    if arg is None:
        return None
    out = []
    for item in arg:
        for p in item.split(","):
            p = p.strip()
            if p:
                out.append(p)
    if not out and any(item == "" or item.strip() == "" for item in arg):
        return ()
    return tuple(out) if out else ()


def cmd_searches(args) -> None:
    from _client import fetch_catalog
    from _shaping import catalog_lines

    prefixes = _parse_excluded_prefixes(getattr(args, "exclude_param_prefix", None))
    cat = fetch_catalog(client(args.site), refresh=args.refresh, excluded_param_prefixes=prefixes)
    print("\n".join(catalog_lines(cat, record_type=args.record_type)))


def cmd_catalog(args) -> None:
    from _client import fetch_catalog
    from _shaping import catalog_lines

    prefixes = _parse_excluded_prefixes(getattr(args, "exclude_param_prefix", None))
    cat = fetch_catalog(client(args.site), refresh=args.refresh, excluded_param_prefixes=prefixes)
    lines = catalog_lines(cat, record_type=args.record_type)
    print(f"# {args.site}: {len(lines)} searches (record_type\tname\tdisplayName\tdescription)")
    print("\n".join(lines))


def cmd_find_searches(args) -> None:
    from _client import fetch_catalog
    from _shaping import score_searches

    prefixes = _parse_excluded_prefixes(getattr(args, "exclude_param_prefix", None))
    cat = fetch_catalog(client(args.site), excluded_param_prefixes=prefixes)
    hits = score_searches(cat, args.query, limit=args.limit)
    if not hits:
        fail(
            f"no searches match '{args.query}'. Broaden the query, or run "
            f"'wdk.py catalog {args.site}' and reason over the full listing "
            "(recommended: in a sub-agent)"
        )
    emit(hits)


def _resolve_or_fail(cat, name, site, client_inst=None):
    from _shaping import resolve_search

    rt, suggestions = resolve_search(cat, name)
    if rt is None:
        if client_inst is not None:
            from _client import fetch_catalog
            raw_cat = fetch_catalog(client_inst, excluded_param_prefixes=())
            raw_rt, _ = resolve_search(raw_cat, name)
            if raw_rt is not None:
                fail(
                    f"search '{name}' on {site} is unavailable: it uses excluded "
                    "parameter prefix(es) (e.g. 'eda_') which are not supported via WDK directly."
                )
        fail(
            f"unknown search '{name}' on {site}. Did you mean: "
            f"{', '.join(suggestions) or '(no close match)'}? "
            f"Run 'wdk.py catalog {site}' for the full list."
        )
    return rt


def cmd_inspect(args) -> None:
    from _client import fetch_catalog
    from _shaping import build_sheet, get_search_detail

    c = client(args.site)
    cat = fetch_catalog(c)
    rt = _resolve_or_fail(cat, args.search, args.site, client_inst=c)
    emit(build_sheet(get_search_detail(c, rt, args.search), query=args.query))


def cmd_inspect_record_type(args) -> None:
    from _client import fetch_record_type
    from _shaping import shape_record_type

    c = client(args.site)
    raw = fetch_record_type(c, args.record_type, refresh=args.refresh)
    f = getattr(args, "filter", None) or getattr(args, "query", None)
    emit(
        shape_record_type(
            raw,
            query=f,
            name_only=getattr(args, "name_only", False),
            exclude=getattr(args, "exclude", None),
        )
    )


def _parse_kv(pairs):
    out = {}
    for pair in pairs or []:
        if "=" not in pair:
            fail(f"--context expects key=value, got '{pair}'")
        k, val = pair.split("=", 1)
        out[k] = val
    return out


def cmd_param_options(args) -> None:
    from _client import fetch_catalog
    from _shaping import get_search_detail, param_options

    c = client(args.site)
    cat = fetch_catalog(c)
    rt = _resolve_or_fail(cat, args.search, args.site, client_inst=c)
    detail = get_search_detail(c, rt, args.search)
    parents = [
        p["name"]
        for p in detail["parameters"]
        if args.param in p.get("dependentParams", [])
    ]
    note = None
    if parents:
        given = _parse_kv(args.context)
        context = {
            name: given.get(
                name,
                next(
                    q.get("initialDisplayValue")
                    for q in detail["parameters"]
                    if q["name"] == name
                ),
            )
            for name in parents
        }
        detail = get_search_detail(c, rt, args.search, context=context)
        used = ", ".join(f"{k}={v}" for k, v in context.items())
        defaulted = [k for k in parents if k not in given]
        note = f"vocabulary read under {used}"
        if defaulted:
            note += (
                f" ({'/'.join(defaulted)} defaulted — pass --context "
                f"{defaulted[0]}=... to change)"
            )
    out = param_options(detail, args.param, query=args.query, limit=args.limit)
    if note and "error" not in out:
        out["context_note"] = note
    emit(out)


def _load_params(raw):
    try:
        params = json.loads(raw)
    except json.JSONDecodeError as e:
        fail(f"--params is not valid JSON: {e}")
    if not isinstance(params, dict):
        fail("--params must be a JSON object of {param: value}")
    return params


def _prepared(args):
    from _client import fetch_catalog
    from _shaping import ParamError, encode_params, get_search_detail_for_params

    c = client(args.site)
    cat = fetch_catalog(c)
    rt = _resolve_or_fail(cat, args.search, args.site, client_inst=c)
    params = _load_params(args.params)
    detail = get_search_detail_for_params(c, rt, args.search, params)
    try:
        wire = encode_params(detail, params, client=c)
    except ParamError as e:
        fail(str(e))
    return c, rt, wire, detail



def cmd_count(args) -> None:
    from _shaping import extract_count, run_report

    c, rt, wire, _ = _prepared(args)
    resp = run_report(c, rt, args.search, wire, num_records=1)
    count, field = extract_count(resp.get("meta", {}))
    emit(
        {
            "search": args.search,
            "count": count if count is not None else "unmeasured",
            "count_field": field,
            "counts": {
                k: resp.get("meta", {}).get(k)
                for k in (
                    "displayViewTotalCount",
                    "viewTotalCount",
                    "displayTotalCount",
                    "totalCount",
                )
            },
        }
    )


def cmd_preview(args) -> None:
    from _shaping import run_report, shape_records

    c, rt, wire, detail = _prepared(args)
    if args.attributes:
        attrs = [a.strip() for a in args.attributes.split(",") if a.strip()]
    else:
        attrs = detail.get("defaultAttributes")
    emit(
        shape_records(
            run_report(c, rt, args.search, wire, num_records=args.limit, attributes=attrs)
        )
    )


def cmd_create_strategy(args) -> None:
    from _client import fetch_catalog
    from _shaping import ParamError
    from _strategy import SpecError, build_strategy

    c = client(args.site)
    try:
        spec = json.loads(args.spec)
    except json.JSONDecodeError as e:
        fail(f"--spec is not valid JSON: {e}")
    try:
        emit(build_strategy(c, fetch_catalog(c), spec, args.name))
    except (SpecError, ParamError) as e:
        fail(str(e))


def cmd_strategy(args) -> None:
    from _strategy import shape_strategy

    c = client(args.site)
    uid = c.user_id()
    emit(shape_strategy(args.site, c.get(f"/users/{uid}/strategies/{args.id}")))


def cmd_list_strategies(args) -> None:
    from _sites import strategy_url

    c = client(args.site)
    uid = c.user_id()
    strategies = c.get(f"/users/{uid}/strategies")
    emit(
        [
            {
                "strategy_id": s.get("strategyId", s.get("id")),
                "name": s.get("name"),
                "url": strategy_url(args.site, s.get("strategyId", s.get("id"))),
            }
            for s in strategies
        ]
    )


def cmd_delete_strategy(args) -> None:
    if not args.yes:
        fail("refusing to delete without --yes")
    c = client(args.site)
    uid = c.user_id()
    c.delete(f"/users/{uid}/strategies/{args.id}")
    emit({"deleted": args.id})


def cmd_results(args) -> None:
    from _shaping import get_search_detail, shape_records

    c = client(args.site)
    uid = c.user_id()
    if args.attributes:
        attrs = [a.strip() for a in args.attributes.split(",") if a.strip()]
    else:
        attrs = ["primary_key"]
        try:
            step = c.get(f"/users/{uid}/steps/{args.step}")
            rt = step.get("recordClassName")
            search_name = step.get("searchName")
            if rt and search_name:
                detail = get_search_detail(c, rt, search_name)
                da = detail.get("defaultAttributes")
                if da:
                    attrs = da
        except Exception:
            pass
    body = {
        "reportConfig": {
            "pagination": {"offset": 0, "numRecords": args.limit},
            "attributes": attrs,
        }
    }
    emit(shape_records(c.post(f"/users/{uid}/steps/{args.step}/reports/standard", body)))


def cmd_download_url(args) -> None:
    from _sites import service_url

    c = client(args.site)
    if args.config:
        try:
            config = json.loads(args.config)
        except json.JSONDecodeError as e:
            fail(f"--config is not valid JSON: {e}")
    else:
        config = {
            "attributes": ["primary_key"],
            "includeHeader": True,
            "attachmentType": "plain",
        }
    resp = c.post(
        "/temporary-results",
        {"stepId": args.step, "reportName": args.report, "reportConfig": config},
        idempotent=False,
    )
    emit({"download_url": f"{service_url(args.site)}/temporary-results/{resp['id']}"})


def cmd_fetch_record(args) -> None:
    from _sites import project_id

    c = client(args.site)
    rt = args.record_type
    if args.primary_key:
        try:
            pk_val = json.loads(args.primary_key)
            if isinstance(pk_val, dict):
                pk = [{"name": k, "value": str(v)} for k, v in pk_val.items()]
            elif isinstance(pk_val, list):
                pk = pk_val
            else:
                fail("--primary-key must be a JSON object or array of {name, value}")
        except json.JSONDecodeError as e:
            fail(f"--primary-key is not valid JSON: {e}")
    elif args.id:
        if rt in ("gene", "organism"):
            pk = [
                {"name": "source_id", "value": args.id},
                {"name": "project_id", "value": project_id(args.site)},
            ]
        elif rt == "transcript":
            if not args.gene_id:
                fail("record-type transcript requires --gene-id or --primary-key")
            pk = [
                {"name": "gene_source_id", "value": args.gene_id},
                {"name": "source_id", "value": args.id},
                {"name": "project_id", "value": project_id(args.site)},
            ]
        else:
            pk = [{"name": "source_id", "value": args.id}]
    else:
        fail("either ID argument or --primary-key is required")

    if args.attributes:
        attrs = [a.strip() for a in args.attributes.split(",") if a.strip()]
    elif rt == "gene":
        attrs = [
            "primary_key",
            "source_id",
            "name",
            "product",
            "organism",
            "gene_type",
            "exon_count",
            "transcript_count",
            "location_text",
        ]
    else:
        attrs = ["primary_key"]

    tbls = [t.strip() for t in args.tables.split(",") if t.strip()] if args.tables else []

    payload = {
        "primaryKey": pk,
        "attributes": attrs,
        "tables": tbls,
    }
    res = c.post(f"/record-types/{rt}/records", payload, idempotent=True)
    from _shaping import shape_record

    emit(shape_record(res, filter_query=getattr(args, "filter", None)))


def cmd_expression(args) -> None:
    from _sites import project_id
    from _shaping import shape_expression_data, OMICS_TYPES

    c = client(args.site)
    gene_id = args.gene.strip()

    omics_cfg = OMICS_TYPES.get(args.type)
    if not omics_cfg:
        fail(f"unknown --type '{args.type}'. Supported types: {list(OMICS_TYPES.keys())}")

    pk = [
        {"name": "source_id", "value": gene_id},
        {"name": "project_id", "value": project_id(args.site)},
    ]
    payload = {
        "primaryKey": pk,
        "attributes": ["primary_key", "name", "product", "organism"],
        "tables": [omics_cfg["graphs_table"], omics_cfg["data_table"]],
    }

    try:
        res = c.post("/record-types/gene/records", payload, idempotent=True)
    except Exception as e:
        err_str = str(e)
        if "404" in err_str or "Not Found" in err_str:
            fail(
                f"gene '{gene_id}' not found on {args.site}.\n"
                f"If this is a gene symbol/name (e.g. 'SRPN5'), resolve the ID first with:\n"
                f"  uv run scripts/wdk.py preview {args.site} GenesByText "
                f"--params '{{\"text_expression\": \"{gene_id}\", \"text_search_organism\": [\"<Organism>\"], \"text_fields\": [\"name\", \"Alias\"]}}' "
                f"--attributes primary_key,gene_name,gene_product"
            )
        raise

    shaped = shape_expression_data(
        res,
        site=args.site,
        omics_type=args.type,
        filter_query=args.filter_query,
        dataset_id=args.dataset_id,
        summary=args.summary,
        top=args.top,
        all_samples=args.all_samples,
        min_percentile=args.min_percentile,
        sort_by=args.sort_by,
        max_datasets=args.max_datasets,
        all_datasets=args.all_datasets,
    )
    emit(shaped)



def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wdk.py", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("sites", help="list site ids, service URLs, project ids")
    sp.set_defaults(func=cmd_sites)

    sp = sub.add_parser("whoami", help="verify token; print numeric user id")
    sp.add_argument("site")
    sp.set_defaults(func=cmd_whoami)

    sp = sub.add_parser("login", help="authenticate and store token in ~/.config/veupathdb/token")
    sp.add_argument("site", nargs="?", default=None, help="target site (default: prompt or veupathdb)")
    sp.add_argument("--token", help="paste API key directly without interactive prompt (or '-' for stdin)")
    sp.add_argument("--token-file", help="read API key from file (e.g. /tmp/<site>-key; keeps secrets out of logs)")
    sp.set_defaults(func=cmd_login)

    sp = sub.add_parser("logout", help="remove stored token from ~/.config/veupathdb/token")
    sp.set_defaults(func=cmd_logout)

    sp = sub.add_parser("detect-site", help="detect VEuPathDB site from query text")
    sp.add_argument("query", help="natural language text or question")
    sp.set_defaults(func=cmd_detect_site)

    sp = sub.add_parser("record-types", help="list record type url segments")
    sp.add_argument("site")
    sp.set_defaults(func=cmd_record_types)

    sp = sub.add_parser("searches", help="list searches for one record type")
    sp.add_argument("site")
    sp.add_argument("record_type")
    sp.add_argument("--refresh", action="store_true", help="bypass 7-day disk cache")
    sp.add_argument(
        "--exclude-param-prefix",
        action="append",
        help="exclude searches with params starting with prefix (default: eda_; pass '' to disable)",
    )
    sp.set_defaults(func=cmd_searches)

    sp = sub.add_parser(
        "catalog",
        help="full compact search catalog (primary discovery input; ~25-75k tokens)",
    )
    sp.add_argument("site")
    sp.add_argument("--record-type")
    sp.add_argument("--refresh", action="store_true")
    sp.add_argument(
        "--exclude-param-prefix",
        action="append",
        help="exclude searches with params starting with prefix (default: eda_; pass '' to disable)",
    )
    sp.set_defaults(func=cmd_catalog)

    sp = sub.add_parser("find-searches", help="lexical search-name lookup (convenience)")
    sp.add_argument("site")
    sp.add_argument("query")
    sp.add_argument("--limit", type=int, default=20)
    sp.add_argument(
        "--exclude-param-prefix",
        action="append",
        help="exclude searches with params starting with prefix (default: eda_; pass '' to disable)",
    )
    sp.set_defaults(func=cmd_find_searches)

    sp = sub.add_parser(
        "inspect-search",
        aliases=["inspect"],
        help="shaped parameter sheet for one search",
    )
    sp.add_argument("site")
    sp.add_argument("search")
    sp.add_argument(
        "--filter",
        "--query",
        dest="query",
        help="hint used to shortlist huge vocabularies",
    )
    sp.set_defaults(func=cmd_inspect)

    sp = sub.add_parser(
        "inspect-record-type",
        help="inspect a record type schema (primary key, attributes, tables)",
    )
    sp.add_argument("site")
    sp.add_argument("record_type")
    sp.add_argument(
        "--filter",
        "--query",
        dest="filter",
        help="filter attributes and tables by keyword",
    )
    sp.add_argument(
        "--name-only",
        action="store_true",
        help="only match filter keyword against attribute/table name, not displayName",
    )
    sp.add_argument(
        "--exclude",
        metavar="PATTERN",
        help="exclude attributes/tables matching pattern (substring or comma-separated, e.g. 'pan_')",
    )
    sp.add_argument(
        "--refresh", action="store_true", help="bypass 7-day disk cache"
    )
    sp.set_defaults(func=cmd_inspect_record_type)

    sp = sub.add_parser(
        "param-options", help="browse/filter a parameter's vocabulary"
    )
    sp.add_argument("site")
    sp.add_argument("search")
    sp.add_argument("param")
    sp.add_argument(
        "--filter",
        "--query",
        dest="query",
        help="case-insensitive substring filter",
    )
    sp.add_argument(
        "--context",
        nargs="*",
        metavar="PARENT=VALUE",
        help="values for params this vocabulary depends on",
    )
    sp.add_argument("--limit", type=int, default=200)
    sp.set_defaults(func=cmd_param_options)

    sp = sub.add_parser("count", help="result count without creating anything (anonymous report)")
    sp.add_argument("site")
    sp.add_argument("search")
    sp.add_argument("--params", required=True, help='JSON object, e.g. \'{"organism": ["Plasmodium"]}\'')
    sp.set_defaults(func=cmd_count)

    sp = sub.add_parser("preview", help="sample records without creating anything")
    sp.add_argument("site")
    sp.add_argument("search")
    sp.add_argument("--params", required=True)
    sp.add_argument("--limit", type=int, default=5)
    sp.add_argument("--attributes", help="comma-separated attribute names")
    sp.set_defaults(func=cmd_preview)

    sp = sub.add_parser("create-strategy", help="create steps + strategy from a declarative JSON spec")
    sp.add_argument("site")
    sp.add_argument("--spec", required=True, help="JSON node tree; see references/strategies.md")
    sp.add_argument("--name", default="wdk.py strategy")
    sp.set_defaults(func=cmd_create_strategy)

    sp = sub.add_parser("strategy", help="strategy detail: tree, counts, url")
    sp.add_argument("site")
    sp.add_argument("id", type=int)
    sp.set_defaults(func=cmd_strategy)

    sp = sub.add_parser("list-strategies", help="list your strategies on a site")
    sp.add_argument("site")
    sp.set_defaults(func=cmd_list_strategies)

    sp = sub.add_parser("delete-strategy", help="delete a strategy (destructive)")
    sp.add_argument("site")
    sp.add_argument("id", type=int)
    sp.add_argument("--yes", action="store_true")
    sp.set_defaults(func=cmd_delete_strategy)

    sp = sub.add_parser("results", help="records for an existing step")
    sp.add_argument("site")
    sp.add_argument("--step", type=int, required=True)
    sp.add_argument("--limit", type=int, default=20)
    sp.add_argument("--attributes")
    sp.set_defaults(func=cmd_results)

    sp = sub.add_parser("download-url", help="temporary download URL for a step's results")
    sp.add_argument("site")
    sp.add_argument("--step", type=int, required=True)
    sp.add_argument("--report", default="attributesTabular")
    sp.add_argument("--config", help="JSON reportConfig override")
    sp.set_defaults(func=cmd_download_url)

    sp = sub.add_parser("fetch-record", help="fetch a single record (e.g. gene) with attributes/tables")
    sp.add_argument("site")
    sp.add_argument("id", nargs="?", help="record primary identifier (e.g. AGAP001212)")
    sp.add_argument("--record-type", default="gene", help="record type (default: gene)")
    sp.add_argument("--gene-id", help="parent gene ID if record-type is transcript")
    sp.add_argument("--primary-key", help="JSON override for primaryKey list/dict")
    sp.add_argument("--attributes", help="comma-separated attribute names")
    sp.add_argument("--tables", help="comma-separated table names (e.g. GeneTranscripts, Orthologs)")
    sp.add_argument(
        "--filter",
        "--query",
        dest="filter",
        help="case-insensitive substring filter for table rows and attributes",
    )
    sp.set_defaults(func=cmd_fetch_record)

    sp = sub.add_parser(
        "expression",
        aliases=["gene-expression"],
        help="transcriptomics & 'omics expression data for a gene (joined datasets + ranked samples)",
    )
    sp.add_argument("site", help="site name (e.g. vectorbase, plasmodb)")
    sp.add_argument("gene", help="gene source ID (e.g. AGAP009221, PF3D7_1127000)")
    sp.add_argument(
        "--type",
        default="expression",
        choices=["expression", "host-response", "phenotype"],
        help="'omics type to query (default: expression)",
    )
    sp.add_argument(
        "--filter",
        "-f",
        dest="filter_query",
        help="filter datasets/samples by keyword (e.g. 'body', 'tissue', 'salivary')",
    )
    sp.add_argument(
        "--dataset",
        "-d",
        dest="dataset_id",
        help="filter to a specific dataset ID (e.g. DS_46d69d95d1) and show all its samples",
    )
    sp.add_argument(
        "--summary",
        action="store_true",
        help="show dataset summary catalog only (omit sample measurements)",
    )
    sp.add_argument(
        "--top",
        "-n",
        type=int,
        default=None,
        help="limit number of samples shown per dataset (default: 5 when displaying samples; all if --dataset)",
    )
    sp.add_argument(
        "--all-samples",
        action="store_true",
        help="show all samples across all matching datasets",
    )
    sp.add_argument(
        "--min-percentile",
        type=float,
        help="filter samples to those with percentile >= cutoff (e.g. 75)",
    )
    sp.add_argument(
        "--sort-by",
        choices=["percentile", "value"],
        default="percentile",
        help="sort samples by 'percentile' (default) or raw abundance 'value'",
    )
    sp.add_argument(
        "--max-datasets",
        type=int,
        default=20,
        help="maximum number of datasets to show in catalog summary (default: 20)",
    )
    sp.add_argument(
        "--all-datasets",
        action="store_true",
        help="show all datasets in catalog summary instead of capping to top datasets",
    )
    sp.set_defaults(func=cmd_expression)

    return p


def main() -> None:
    from _client import WDKError

    args = build_parser().parse_args()
    try:
        args.func(args)
    except (UnknownSiteError, WDKError) as e:
        fail(str(e))


if __name__ == "__main__":
    main()
