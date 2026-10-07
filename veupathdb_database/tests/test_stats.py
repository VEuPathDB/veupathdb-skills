import pytest


def test_pearson_and_zero_variance():
    from _stats import pearson

    assert pearson([1, 2, 3, 4], [2, 4, 6, 8]) == pytest.approx(1.0)
    assert pearson([1, 2, 3, 4], [8, 6, 4, 2]) == pytest.approx(-1.0)
    assert pearson([1, 1, 1], [1, 2, 3]) is None


def test_eta_squared_simple():
    from _stats import eta_squared

    assert eta_squared(["a", "a", "b", "b"], [1.0, 1.0, 3.0, 3.0]) == pytest.approx(1.0)
    assert eta_squared(["a", "b", "a", "b"], [1.0, 1.0, 3.0, 3.0]) == pytest.approx(0.0)
    assert eta_squared(["a", "b"], [2.0, 2.0]) is None


@pytest.mark.parametrize(
    "kind, values, pc, reason",
    [
        ("categorical", ["a", None, None, "b"], [1.0, 2.0, 3.0, 4.0], "fewer than 3"),
        ("categorical", ["a"] * 5, [1.0, 2.0, 3.0, 4.0, 5.0], "constant"),
        ("continuous", [2.0] * 4, [1.0, 2.0, 3.0, 4.0], "constant"),
        ("categorical", ["a", "a", "b", "b"], [1.0, 1.0, 1.0, 1.0], "zero variance"),
        ("categorical", ["a", "b", "c", "d"], [1.0, 2.0, 3.0, 4.0], "eta² would be 1"),
    ],
)
def test_score_edge_cases_are_reported_not_scored(kind, values, pc, reason):
    from _stats import score_against_pc

    out = score_against_pc(kind, values, pc)
    assert reason in out["not_scored"] and "value" not in out


def test_score_categorical_with_a_singleton_level_is_scored():
    from _stats import score_against_pc

    out = score_against_pc("categorical", ["a", "a", "b", "c"], [1.0, 1.2, 3.0, 5.0])
    assert out["stat"] == "eta2" and out["levels"] == 3 and out["n"] == 4
    assert 0 < out["value"] <= 1


def test_score_continuous():
    from _stats import score_against_pc

    out = score_against_pc("continuous", [1.0, 2.0, None, 4.0], [2.0, 4.1, 9.0, 7.9])
    assert out["stat"] == "r" and out["n"] == 3
    assert out["r2"] == pytest.approx(out["r"] ** 2) == out["value"]


def test_outliers_flags_a_far_point():
    from _stats import outliers

    out = outliers(_pca_like(12))
    assert [s["sampleId"] for s in out["samples"]] == ["far"]
    assert out["samples"][0]["distance"] > 3 and out["pcs"] == 2


def _pca_like(n):
    """Centred, uncorrelated 2-PC scores with one sample as far out as n allows on PC1."""
    others = n - 1
    pc2 = [(-1.0) ** i for i in range(others - others % 2)] + [0.0] * (others % 2)
    pts = {"far": [float(others), 0.0]}
    pts |= {f"s{i}": [-1.0, v] for i, v in enumerate(pc2)}
    for k in range(2):
        assert sum(p[k] for p in pts.values()) == 0
    assert sum(p[0] * p[1] for p in pts.values()) == 0
    return pts


@pytest.mark.parametrize("n,scored", [(10, False), (11, True), (12, True)])
def test_outliers_reachability_bound(n, scored):
    """Uncorrelated PC scores cap any sample's distance at (n-1)/sqrt(n) whatever the
    number of PCs, so with threshold 3 nothing is reachable below n=11."""
    from _stats import outliers

    out = outliers(_pca_like(n))
    if scored:
        assert "not_scored" not in out and [s["sampleId"] for s in out["samples"]] == ["far"]
        assert out["samples"][0]["distance"] == pytest.approx((n - 1) / n ** 0.5, abs=0.01)
    else:
        assert f"n={n}" in out["not_scored"] and "3" in out["not_scored"] and out["samples"] == []


def test_outliers_not_scored_cases():
    from _stats import outliers

    assert "fewer than 5" in outliers({"a": [1.0, 2.0], "b": [2.0, 1.0]})["not_scored"]
    flat = {f"s{i}": [1.0, float(i)] for i in range(6)}
    assert "zero SD" in outliers(flat)["not_scored"]
    with_missing = {f"s{i}": [float(i), float(i % 3)] for i in range(12)}
    with_missing["s99"] = [None, 1.0]
    out = outliers(with_missing)
    assert "not_scored" not in out and out["pcs"] == 2 and out["samples"] == []
    small = _pca_like(6)  # n=6: no point can reach distance 3, however many PCs
    out = outliers(small)
    assert "too few samples" in out["not_scored"] and out["samples"] == []


def test_outliers_rejects_inconsistent_pc_counts():
    from _stats import outliers

    with pytest.raises(ValueError):
        outliers({f"s{i}": [float(i), 1.0] for i in range(6)} | {"x": [1.0]})


def test_score_rejects_unknown_kind():
    from _stats import score_against_pc

    with pytest.raises(ValueError):
        score_against_pc("ordinal", ["a", "a", "b"], [1.0, 2.0, 3.0])
