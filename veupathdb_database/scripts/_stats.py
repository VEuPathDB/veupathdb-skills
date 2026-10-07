"""Statistics for eda.py, standard library only. Base R is the test-time gold
standard (tests/test_stats_r.py); nothing here needs R at use time."""
import math
from collections import Counter, defaultdict

MIN_SCORED_N = 3
MIN_OUTLIER_N = 5
OUTLIER_Z = 3.0


def mean(xs):
    return math.fsum(xs) / len(xs)


def sum_sq(xs):
    m = mean(xs)
    return math.fsum((x - m) ** 2 for x in xs)


def pearson(xs, ys):
    """Pearson r, or None when either side has zero variance."""
    mx, my = mean(xs), mean(ys)
    sxx = math.fsum((x - mx) ** 2 for x in xs)
    syy = math.fsum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return None
    sxy = math.fsum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return sxy / math.sqrt(sxx * syy)


def eta_squared(groups, ys):
    """One-way ANOVA eta² = SS_between / SS_total (= R² of lm(y ~ factor(g)))."""
    total = sum_sq(ys)
    if total == 0:
        return None
    by = defaultdict(list)
    for g, y in zip(groups, ys):
        by[g].append(y)
    m = mean(ys)
    between = math.fsum(len(v) * (mean(v) - m) ** 2 for v in by.values())
    return between / total


def score_against_pc(kind, values, pc):
    """Association of one sample variable with one PC, or a 'not scored' reason.
    Samples missing either value are dropped first; n is what remains."""
    pairs = [(x, y) for x, y in zip(values, pc) if x is not None and y is not None]
    n = len(pairs)
    if n < MIN_SCORED_N:
        return {"n": n, "not_scored": f"fewer than {MIN_SCORED_N} samples with a value"}
    xs = [x for x, _ in pairs]
    ys = [y for _, y in pairs]
    counts = Counter(xs)
    if len(counts) < 2:
        return {"n": n, "not_scored": "constant: one distinct value among these samples"}
    if sum_sq(ys) == 0:
        return {"n": n, "not_scored": "PC has zero variance"}
    if kind == "continuous":
        r = pearson(xs, ys)
        return {"stat": "r", "r": r, "r2": r * r, "value": r * r, "n": n}
    if max(counts.values()) < 2:
        return {"n": n, "levels": len(counts),
                "not_scored": "no level has 2+ samples: eta² would be 1 by construction"}
    e = eta_squared(xs, ys)
    return {"stat": "eta2", "eta2": e, "value": e, "n": n, "levels": len(counts)}


def outliers(points, threshold=OUTLIER_Z, min_n=MIN_OUTLIER_N):
    """points: {sampleId: [pc1, pc2, …]}. Flags samples whose standardised distance
    sqrt(sum_k z_k²) from the centroid exceeds `threshold` (z per PC, sample SD)."""
    complete = {s: p for s, p in points.items() if p and all(v is not None for v in p)}
    if len(complete) < min_n:
        return {"not_scored": f"fewer than {min_n} samples with scores", "samples": []}
    dims = len(next(iter(complete.values())))
    cols = [[p[k] for p in complete.values()] for k in range(dims)]
    means = [mean(c) for c in cols]
    sds = [math.sqrt(sum_sq(c) / (len(c) - 1)) for c in cols]
    if any(sd == 0 for sd in sds):
        return {"not_scored": "a PC has zero SD", "samples": []}
    flagged = []
    for s, p in complete.items():
        d = math.sqrt(math.fsum(((v - m) / sd) ** 2 for v, m, sd in zip(p, means, sds)))
        if d > threshold:
            flagged.append({"sampleId": s, "distance": round(d, 2)})
    return {"threshold": threshold, "pcs": dims, "samples": sorted(flagged, key=lambda f: -f["distance"])}
