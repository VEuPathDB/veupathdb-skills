"""R gold standard for _stats.py: base R's cor() and lm() on the same inputs.
R is a development dependency only; these tests skip without Rscript."""
import csv
import shutil
import subprocess

import pytest
from eda_helpers import eda_fixture

RSCRIPT = shutil.which("Rscript")
pytestmark = pytest.mark.skipif(
    RSCRIPT is None, reason="Rscript not on PATH: the R gold-standard tests need base R (development only)"
)
TOL = 1e-9  # relative; near-constant inputs lose precision in any implementation
NEAR_CONSTANT_TOL = 1e-5


def r_value(tmp_path, rows, expr):
    """Evaluate a numeric R expression over d (columns g, x, y; NA for None)."""
    path = tmp_path / "d.csv"
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["g", "x", "y"])
        for g, x, y in rows:
            w.writerow(["NA" if g is None else g,
                        "NA" if x is None else repr(float(x)),
                        "NA" if y is None else repr(float(y))])
    code = (f'd <- read.csv("{path}", stringsAsFactors=FALSE, na.strings="NA", '
            f'colClasses=c("character","numeric","numeric")); cat(sprintf("%.17g", {expr}))')
    out = subprocess.run([RSCRIPT, "--vanilla", "-e", code], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def close(a, b, tol):
    return abs(a - b) <= tol * max(1.0, abs(b))


def complete(*cols):
    keep = [row for row in zip(*cols) if all(v is not None for v in row)]
    return [list(c) for c in zip(*keep)]


PEARSON = {
    "missing": ([1, 2, None, 4, 5, 6], [2.1, 3.9, 6.2, None, 9.8, 12.5], TOL),
    "ties": ([1, 1, 2, 2, 3, 3], [0.5, 0.7, 0.2, 0.9, 1.5, 1.1], TOL),
    "negative": ([10, 20, 30, 40], [4.0, 3.5, 1.0, 0.2], TOL),
    "near_constant": ([1, 1, 1, 1, 1 + 1e-9], [3.0, 1.0, 4.0, 1.0, 5.0], NEAR_CONSTANT_TOL),
}
ETA = {
    "missing": (["a", "a", None, "b", "b", "c", "c"], [1.0, 1.4, 9.0, 3.0, None, 5.5, 5.1], TOL),
    "singleton_level": (["a", "a", "a", "b", "b", "c"], [1.0, 2.0, 1.5, 4.0, 4.4, 9.0], TOL),
    "ties": (["a", "a", "b", "b", "c", "c"], [1.0, 1.0, 2.0, 2.0, 2.0, 3.0], TOL),
    "near_constant": (["a", "a", "b", "b"], [1.0, 1.0, 1.0, 1.0 + 1e-9], NEAR_CONSTANT_TOL),
}


@pytest.mark.parametrize("case", sorted(PEARSON))
def test_pearson_matches_r(tmp_path, case):
    from _stats import pearson

    xs, ys, tol = PEARSON[case]
    want = r_value(tmp_path, [("a", x, y) for x, y in zip(xs, ys)], 'cor(d$x, d$y, use="complete.obs")')
    got = pearson(*complete(xs, ys))
    assert close(got, want, tol), (got, want)


@pytest.mark.parametrize("case", sorted(ETA))
def test_eta_squared_matches_r(tmp_path, case):
    from _stats import eta_squared

    gs, ys, tol = ETA[case]
    want = r_value(tmp_path, [(g, 0, y) for g, y in zip(gs, ys)], "summary(lm(y ~ factor(g), data=d))$r.squared")
    got = eta_squared(*complete(gs, ys))
    assert close(got, want, tol), (got, want)


def _heatshock():
    pcs = {}
    for line in eda_fixture("pca_heatshock_tabular.tsv").strip().splitlines()[1:]:
        cells = line.split("\t")
        pcs[cells[0]] = (float(cells[1]), float(cells[2]))
    tab = eda_fixture("tabular_heatshock_sample.json")
    rows = [dict(zip(tab[0], r)) for r in tab[1:]]
    return rows, pcs, tab[0][0]


@pytest.mark.parametrize("var, k, expected", [("VAR_081ab087", 0, 0.7751), ("VAR_26d10fbf", 1, 0.4964)])
def test_heatshock_eta_squared_matches_r(tmp_path, var, k, expected):
    from _stats import eta_squared

    rows, pcs, key = _heatshock()
    gs = [r[var] for r in rows]
    ys = [pcs[r[key]][k] for r in rows]
    want = r_value(tmp_path, [(g, 0, y) for g, y in zip(gs, ys)], "summary(lm(y ~ factor(g), data=d))$r.squared")
    got = eta_squared(gs, ys)
    assert close(got, want, TOL)
    assert round(got, 4) == expected  # Verified live facts


def test_heatshock_pearson_temperature_matches_r(tmp_path):
    from _stats import pearson

    rows, pcs, key = _heatshock()
    xs = [float(r["VAR_7033e90f"]) for r in rows]
    ys = [pcs[r[key]][0] for r in rows]
    want = r_value(tmp_path, [("a", x, y) for x, y in zip(xs, ys)], "cor(d$x, d$y)")
    got = pearson(xs, ys)
    assert close(got, want, TOL)
    assert round(got * got, 4) == 0.7751  # binary, so r² equals the live eta² on PC1
