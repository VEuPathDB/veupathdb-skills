"""DE result shaping, the WSF plugin's threshold logic and the eda_analysis_spec builder (pure functions; no I/O)."""
import difflib
import json
import math
import re

from _contrasts import METHODS, PLUGIN_DE, PLUGIN_PCA, canonical_filters
from _eda import EdaError

DIRECTIONS = ("upAndDown", "upOnly", "downOnly")
DEFAULT_THRESHOLDS = "1,0.05,upAndDown"
_JAVA_DOUBLE = re.compile(r"[+-]?(NaN|Infinity|(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?[fFdD]?)")


class SpecError(EdaError):
    pass


def java_double(value):
    """Parse like Java Double.valueOf, which the plugin uses; None where Java throws.
    (Python's float() also takes 'nan', 'inf' and 'NA'-free spellings Java rejects.)"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not _JAVA_DOUBLE.fullmatch(s):
        return None
    return float(s.rstrip("fFdD"))


def _java_repr(x):
    if math.isinf(x):
        return "Infinity" if x > 0 else "-Infinity"
    return repr(x)


def negate_effects(statistics):
    """Statistics of the mirror contrast (groupA and groupB swapped): with a two-level
    ~comparator design and no shrinkage, DESeq2 results() and limma topTable(coef=2)
    give the same p and padj with effectSize negated (infinities in Java's spelling).
    Unparseable and NaN values, and zero, pass through unchanged."""
    out = []
    for s in statistics:
        x = java_double(s.get("effectSize"))
        if x is not None and not math.isnan(x) and x:
            s = {**s, "effectSize": _java_repr(-x)}
        out.append(s)
    return out


def parse_thresholds(text):
    parts = [p.strip() for p in str(text).split(",")]
    if len(parts) not in (2, 3):
        raise EdaError("--thresholds expects FC,P[,upAndDown|upOnly|downOnly], e.g. 1,0.05")
    try:
        fc, p = float(parts[0]), float(parts[1])
    except ValueError:
        raise EdaError(f"--thresholds: FC and P must be numbers, got {text!r}") from None
    if not math.isfinite(fc):
        raise EdaError(f"--thresholds: FC and P must be numbers, got {text!r}")
    direction = parts[2] if len(parts) == 3 else "upAndDown"
    if direction not in DIRECTIONS:
        hint = difflib.get_close_matches(direction, DIRECTIONS, n=1, cutoff=0.3)
        raise EdaError(f"--thresholds direction {direction!r}; did you mean {hint}? one of {list(DIRECTIONS)}")
    if fc < 0 or not 0 < p <= 1:
        raise EdaError("--thresholds: FC must be >= 0 and P in (0, 1]")
    return fc, p, direction


def is_retained(effect_size, p_value, fc, p, direction):
    """Exact port of GeneEdaVizWithComputePlugin.isRetainedRow: raw p, inclusive bounds."""
    raw, pv = java_double(effect_size), java_double(p_value)
    if raw is None or pv is None:
        return False
    if not (abs(pv) <= p and abs(raw) >= fc):
        return False
    if direction == "upOnly":
        return raw > 0
    if direction == "downOnly":
        return raw < 0
    return True


def wdk_step_genes(statistics, thresholds):
    """Genes the WDK step returns. The plugin writes the statistics with no header line,
    then skips the first line as if it were one (AbstractEdaGenesPlugin.execute), so
    statistics[0] never reaches the step. Verified live: 5510 retained -> 5509 returned."""
    fc, p, direction = thresholds
    return [
        s.get("pointID")
        for s in statistics[1:]
        if is_retained(s.get("effectSize"), s.get("pValue"), fc, p, direction)
    ]


def _finite(x):
    return x if x is not None and math.isfinite(x) else None


def de_table(statistics):
    return [
        {
            "gene": s.get("pointID"),
            "effectSize": _finite(java_double(s.get("effectSize"))),
            "pValue": _finite(java_double(s.get("pValue"))),
            "adjustedPValue": _finite(java_double(s.get("adjustedPValue"))),
        }
        for s in statistics
    ]


def summarise(statistics, thresholds, top_n=10):
    fc, p, direction = thresholds
    table = de_table(statistics)
    raw = [
        s.get("pointID")
        for s in statistics
        if is_retained(s.get("effectSize"), s.get("pValue"), fc, p, direction)
    ]
    first = statistics[0] if statistics else None
    dropped = None
    if first and is_retained(first.get("effectSize"), first.get("pValue"), fc, p, direction):
        dropped = first.get("pointID")
    padj = [
        r
        for r in table
        if r["effectSize"] is not None
        and r["adjustedPValue"] is not None
        and is_retained(r["effectSize"], r["adjustedPValue"], fc, p, direction)
    ]
    up = sorted((r for r in padj if r["effectSize"] > 0), key=lambda r: (-r["effectSize"], r["gene"]))[:top_n]
    down = sorted((r for r in padj if r["effectSize"] < 0), key=lambda r: (r["effectSize"], r["gene"]))[:top_n]
    return {
        "tested": len(table),
        "padj_na": sum(1 for r in table if r["adjustedPValue"] is None),
        "passing_raw_p": len(raw),
        "wdk_step_genes": len(wdk_step_genes(statistics, thresholds)),
        "wdk_dropped_gene": dropped,
        "passing_padj": len(padj),
        "passing_raw_genes": raw,
        "top_up": up,
        "top_down": down,
    }


def gene_rows(table, genes):
    by_lower = {r["gene"].lower(): r for r in table if r["gene"]}
    out = []
    for g in genes:
        r = by_lower.get(g.lower())
        if r is None:
            out.append({"gene": g, "effectSize": None, "pValue": None, "adjustedPValue": None,
                        "status": "not tested (absent from the output: all-zero counts, or not measured)"})
        elif r["adjustedPValue"] is None:
            out.append({**r, "status": "tested; padj NA (removed by independent filtering, usually low counts)"})
        else:
            out.append({**r, "status": "tested"})
    return out


def de_json(context, provenance, summary, table, genes=()):
    """identity / context / provenance / rows. A blind consumer drops `identity` only;
    row keys are opaque (r1, r2, … in p-value order)."""
    wanted = [r["gene"] for r in summary["top_up"] + summary["top_down"]]
    if summary["wdk_dropped_gene"]:
        wanted.append(summary["wdk_dropped_gene"])
    wanted += list(genes)
    seen, unique = set(), []
    for g in wanted:
        if g.lower() not in seen:
            seen.add(g.lower())
            unique.append(g)
    rows = gene_rows(table, unique)
    rows.sort(key=lambda r: (r["pValue"] if r["pValue"] is not None else 2.0, r["gene"]))
    key_of = {r["gene"]: f"r{i}" for i, r in enumerate(rows, 1)}
    ctx = {
        **context,
        "counts": {k: summary[k] for k in ("tested", "padj_na", "passing_raw_p", "wdk_step_genes", "passing_padj")},
        "top": {
            "up": [key_of[r["gene"]] for r in summary["top_up"]],
            "down": [key_of[r["gene"]] for r in summary["top_down"]],
        },
    }
    if summary["wdk_dropped_gene"]:
        ctx["wdkDroppedRow"] = key_of[summary["wdk_dropped_gene"]]
    return {
        "context": ctx,
        "provenance": provenance,
        "identity": {key_of[r["gene"]]: r["gene"] for r in rows},
        "rows": {key_of[r["gene"]]: {k: v for k, v in r.items() if k != "gene"} for r in rows},
    }


def table_tsv(table):
    lines = ["gene\teffectSize\tpValue\tadjustedPValue"]
    for r in table:
        cells = ["NA" if r[k] is None else repr(r[k]) for k in ("effectSize", "pValue", "adjustedPValue")]
        lines.append("\t".join([r["gene"]] + cells))
    return "\n".join(lines) + "\n"


def _g(x, spec):
    return "NA" if x is None else format(x, spec)


def render_de(context, provenance, summary, gene_count=None, genes=None, next_hint=None):
    a, b, t = context["groupA"], context["groupB"], context["thresholds"]
    lines = [
        f"contrast {provenance['jobId']} (the EDA job id: cite it as the contrast id)",
        f"{provenance['datasetId']} \"{context['study']}\"  {context['method']} on {context['valueVariable']}",
        f"{context['comparator']['variable']}: groupA (reference) {'+'.join(a['labels'])} n={a['n']} → "
        f"groupB {'+'.join(b['labels'])} n={b['n']}; positive log2FC = higher in groupB (unshrunk)",
        f"filters: {json.dumps(context['filters']) if context['filters'] else 'none'}",
    ]
    absent = f" ({gene_count - summary['tested']} genes absent: not tested)" if gene_count else ""
    lines.append(f"tested {summary['tested']} genes{absent}; padj NA: {summary['padj_na']}")
    lines.append(f"thresholds |log2FC| >= {t['effectSize']:g}, raw p <= {t['pValue']:g}, {t['direction']}")
    lines.append(f"passing raw p: {summary['passing_raw_p']}  → the WDK step returns {summary['wdk_step_genes']} genes")
    if summary["wdk_dropped_gene"]:
        lines.append(
            f"  (the WDK plugin drops the first statistics row, {summary['wdk_dropped_gene']}, "
            "which passes: a known upstream quirk)"
        )
    lines.append(f"passing padj: {summary['passing_padj']}")
    for name, rows in (("up", summary["top_up"]), ("down", summary["top_down"])):
        if rows:
            lines.append(
                f"top {name} (passing padj): "
                + ", ".join(f"{r['gene']} {r['effectSize']:+.2f} (padj {r['adjustedPValue']:.2g})" for r in rows)
            )
    lines += [f"note: {n}" for n in context["notes"]]
    if genes:
        lines.append("genes:")
        for r in genes:
            lines.append(
                f"  {r['gene']}: {r['status']}; log2FC {_g(r['effectSize'], '+.3f')} "
                f"p {_g(r['pValue'], '.3g')} padj {_g(r['adjustedPValue'], '.3g')}"
            )
    if next_hint:
        lines.append(next_hint)
    return lines


def build_spec(dataset_id, display_name, filters, de_cfg, pca_cfg, thresholds):
    """The eda_analysis_spec the website notebook saves: subset filters, pca_1 and de_1
    computations, and a volcano visualization carrying the thresholds."""
    fc, p, direction = thresholds
    return {
        "displayName": display_name,
        "description": "",
        "studyId": dataset_id,
        "studyVersion": "",
        "apiVersion": "",
        "isPublic": False,
        "descriptor": {
            "subset": {"descriptor": canonical_filters(filters), "uiSettings": {}},
            "computations": [
                {
                    "computationId": "pca_1",
                    "descriptor": {"type": PLUGIN_PCA, "configuration": pca_cfg},
                    "visualizations": [
                        {"visualizationId": "pca_1", "displayName": "PCA Plot",
                         "descriptor": {"type": "scatterplot", "configuration": {}}}
                    ],
                },
                {
                    "computationId": "de_1",
                    "descriptor": {"type": PLUGIN_DE, "configuration": de_cfg},
                    "visualizations": [
                        {"visualizationId": "volcano_1", "displayName": "Volcano Plot",
                         "descriptor": {"type": "volcanoplot", "configuration": {
                             "effectSizeThreshold": fc, "significanceThreshold": p, "effectDirection": direction}}}
                    ],
                },
            ],
            "starredVariables": [],
            "dataTableConfig": {},
            "derivedVariables": [],
        },
    }


def find_volcano_computation(computations):
    """Port of the plugin's findVolcanoComputation: first computation with a volcanoplot
    visualization whose configuration has both thresholds."""
    for comp in computations or []:
        for viz in comp.get("visualizations") or []:
            desc = viz.get("descriptor") or {}
            cfg = desc.get("configuration")
            if desc.get("type") == "volcanoplot" and isinstance(cfg, dict) and \
                    "effectSizeThreshold" in cfg and "significanceThreshold" in cfg:
                return comp
    return None


def validate_spec(spec, dataset_id):
    """The rules GeneEdaVizWithComputePlugin and the DE compute apply, checked before printing."""
    if spec.get("studyId") != dataset_id:
        raise SpecError(
            f"spec studyId {spec.get('studyId')!r} must equal eda_dataset_id {dataset_id!r} "
            "(a DS_ dataset id, not a STUDY_ id)"
        )
    try:
        filters = spec["descriptor"]["subset"]["descriptor"]
        computations = spec["descriptor"]["computations"]
    except (KeyError, TypeError):
        raise SpecError("spec needs descriptor.subset.descriptor and descriptor.computations") from None
    if not isinstance(filters, list):
        raise SpecError("descriptor.subset.descriptor must be a list of filters")
    comp = find_volcano_computation(computations)
    if comp is None:
        raise SpecError("no computation has a volcanoplot visualization with effectSizeThreshold and significanceThreshold")
    if comp["visualizations"][0].get("descriptor", {}).get("type") != "volcanoplot":
        raise SpecError("the plugin reads thresholds from the first visualization of the volcano computation; put the volcano plot first")
    if comp["descriptor"].get("type") != PLUGIN_DE:
        raise SpecError(f"the volcano computation must be {PLUGIN_DE}, got {comp['descriptor'].get('type')!r}")
    cfg = comp["descriptor"].get("configuration") or {}
    for key in ("identifierVariable", "valueVariable", "comparator"):
        if not cfg.get(key):
            raise SpecError(f"differentialexpression configuration is missing {key}")
    for key in ("groupA", "groupB"):
        if not cfg["comparator"].get(key):
            raise SpecError(f"comparator {key} is empty")
    if cfg["identifierVariable"].get("entityId") != cfg["valueVariable"].get("entityId"):
        raise SpecError("identifier and value variables must be on the same entity")
    if cfg.get("differentialExpressionMethod") not in METHODS:
        raise SpecError(f"differentialExpressionMethod must be one of {METHODS}")


def wdk_params(spec):
    """WDK params for the DE/antibody-array search; the spec travels as a JSON string."""
    return {"eda_dataset_id": spec["studyId"], "eda_analysis_spec": json.dumps(spec, separators=(",", ":"), ensure_ascii=False)}
