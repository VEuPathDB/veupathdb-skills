"""Shared test helpers for eda.py: captured fixtures, a synthetic study, a fake EDA service."""
import json
import pathlib

import httpx

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "eda"


def eda_fixture(name):
    path = FIXTURES / name
    text = path.read_text(encoding="utf-8")
    return text if path.suffix == ".tsv" else json.loads(text)


def _matches(cell, f):
    if f["type"] == "stringSet":
        return cell in f["stringSet"]
    if f["type"] == "numberRange":
        try:
            return f["min"] <= float(cell) <= f["max"]
        except ValueError:
            return False
    return True


def synthetic_study():
    """Participant -> Sample -> counts. Exercises hidden variables, categories,
    ordering, long definitions, and an ancestor join."""
    return {
        "id": "STUDY_x",
        "rootEntity": {
            "id": "ENT_p",
            "displayName": "Participant",
            "variables": [
                {"id": "VAR_sex", "parentId": "ENT_p", "displayName": "sex", "type": "string",
                 "dataShape": "categorical", "vocabulary": ["female", "male"], "displayOrder": 1},
                {"id": "VAR_hide", "parentId": "ENT_p", "displayName": "internal", "type": "string",
                 "dataShape": "categorical", "hideFrom": ["everywhere"]},
            ],
            "children": [
                {
                    "id": "ENT_s",
                    "displayName": "Sample",
                    "variables": [
                        {"id": "VAR_cat", "parentId": "ENT_s", "displayName": "Condition group", "type": "category"},
                        {"id": "VAR_cond", "parentId": "VAR_cat", "displayName": "condition", "type": "string",
                         "dataShape": "categorical", "isFeatured": True, "vocabulary": ["control", "treated"],
                         "displayOrder": 2, "definition": "x" * 200},
                        {"id": "VAR_dose", "parentId": "VAR_cat", "displayName": "dose", "type": "number",
                         "dataShape": "continuous", "units": "mg", "displayOrder": 1, "definition": "",
                         "distributionDefaults": {"rangeMin": 0, "rangeMax": 10, "binWidth": 1}},
                        {"id": "VAR_emptycat", "parentId": "ENT_s", "displayName": "Nothing here", "type": "category"},
                    ],
                    "children": [
                        {
                            "id": "ENT_g",
                            "displayName": "counts",
                            "variables": [
                                {"id": "VEUPATHDB_GENE_ID", "parentId": "ENT_g", "type": "string",
                                 "dataShape": "categorical", "distinctValuesCount": 100},
                                {"id": "SEQUENCE_READ_COUNT", "parentId": "ENT_g", "type": "integer",
                                 "dataShape": "continuous"},
                            ],
                        }
                    ],
                }
            ],
        },
    }


class EdaMock:
    """Fake EDA service for the heat-shock study, served from captured fixtures.

    Filters on sample variables are applied to the captured sample tabular, which
    is enough for stringSet/numberRange tests. Override a route with
    mock.routes[(METHOD, path_without_/eda)] = fn(request) -> httpx.Response.
    """

    STUDY = "STUDY_e973eadd57"
    SAMPLE = "ENT_8151325d"

    def __init__(self):
        jobs = eda_fixture("jobs.json")
        self.de_job = jobs["de_heatshock"]["jobID"]
        self.pca_job = jobs["pca_heatshock"]["jobID"]
        self.requests = []
        self.routes = {}

    def sample_rows(self, filters):
        rows = eda_fixture("tabular_heatshock_sample.json")
        header, data = rows[0], rows[1:]
        for f in filters:
            if f.get("variableId") in header:
                col = header.index(f["variableId"])
                data = [r for r in data if _matches(r[col], f)]
        return [header] + data

    def compute_bodies(self, plugin):
        return [b for m, p, q, b in self.requests if p == f"/computes/{plugin}"]

    def handler(self, request):
        path = request.url.path.removeprefix("/eda")
        body = json.loads(request.content) if request.content else None
        self.requests.append((request.method, path, dict(request.url.params), body))
        custom = self.routes.get((request.method, path))
        if custom:
            return custom(request)
        text = {"content-type": "text/plain"}
        if path == "/permissions":
            return httpx.Response(200, json=eda_fixture("permissions.json"))
        if path == f"/studies/{self.STUDY}":
            return httpx.Response(200, json={"study": eda_fixture("study_heatshock.json")})
        if path == f"/studies/{self.STUDY}/entities/{self.SAMPLE}/tabular":
            return httpx.Response(200, json=self.sample_rows(body["filters"]))
        if path.startswith(f"/studies/{self.STUDY}/entities/") and path.endswith("/count"):
            return httpx.Response(200, json={"count": len(self.sample_rows(body["filters"])) - 1})
        if path == "/computes/differentialexpression":
            return httpx.Response(200, json={"jobID": self.de_job, "status": "complete"})
        if path == "/apps/differentialexpression/visualizations/volcanoplot":
            return httpx.Response(200, json=eda_fixture("volcano_heatshock.json"))
        if path == "/computes/dimensionalityreduction":
            return httpx.Response(200, json={"jobID": self.pca_job, "status": "complete"})
        if path == "/computes/dimensionalityreduction/tabular":
            return httpx.Response(200, text=eda_fixture("pca_heatshock_tabular.tsv"), headers=text)
        if path == "/computes/dimensionalityreduction/meta":
            return httpx.Response(200, text=json.dumps(eda_fixture("pca_heatshock_meta.json")), headers=text)
        if path.endswith("/distribution"):
            if "binSpec" in body:
                return httpx.Response(200, json={"histogram": [], "statistics": {
                    "subsetSize": 12, "subsetMin": 37, "subsetMax": 41, "subsetMean": 39,
                    "numVarValues": 12, "numDistinctValues": 2, "numMissingCases": 0}})
            return httpx.Response(200, json={
                "histogram": [{"binLabel": "febrile", "value": 6}, {"binLabel": "normal", "value": 6}],
                "statistics": {"numVarValues": 12, "numDistinctValues": 2, "numMissingCases": 0}})
        return httpx.Response(404, json={"status": "not-found", "path": path})
