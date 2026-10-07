"""EDA endpoint wrappers. `c` is a Client from _client.eda_client()."""
import difflib
import sys
import time

from _client import cached_json
from _shaping import strip_html

RUNNING = ("queued", "in-progress")


class EdaError(Exception):
    pass


def _permissions(c, refresh):
    return cached_json(f"{c.site_id}_permissions", lambda: c.get("/permissions"), refresh=refresh)


def resolve_dataset(c, dataset_id, refresh=False):
    """DS_ id -> the STUDY_ id EDA endpoints need, plus display name and description."""
    per = _permissions(c, refresh).get("perDataset") or {}
    if dataset_id not in per and not refresh:
        per = _permissions(c, True).get("perDataset") or {}
    if dataset_id not in per:
        close = difflib.get_close_matches(dataset_id, list(per), n=3, cutoff=0.8)
        raise EdaError(
            f"dataset '{dataset_id}' is not visible to this user on {c.site_id} "
            f"(missing from /eda/permissions). Check the login ('wdk.py whoami {c.site_id}') "
            "and the site."
            + (f" Close ids: {close}" if close else "")
        )
    entry = per[dataset_id]
    return {
        "datasetId": dataset_id,
        "studyId": entry["studyId"],
        "displayName": entry.get("displayName") or "",
        "shortDisplayName": entry.get("shortDisplayName") or "",
        "description": strip_html(entry.get("description") or ""),
    }


def study_metadata(c, study_id, refresh=False):
    return cached_json(
        f"{c.site_id}_study_{study_id}",
        lambda: c.get(f"/studies/{study_id}")["study"],
        refresh=refresh,
    )


def entity_count(c, study_id, entity_id, filters):
    return int(c.post(f"/studies/{study_id}/entities/{entity_id}/count", {"filters": filters})["count"])


def tabular(c, study_id, entity_id, variable_ids, filters):
    """Rows as string lists, header first: own key, ancestor keys (nearest first), variables."""
    data = c.post(
        f"/studies/{study_id}/entities/{entity_id}/tabular",
        {"filters": filters, "outputVariableIds": list(variable_ids)},
    )
    if isinstance(data, str):
        return [line.split("\t") for line in data.splitlines() if line]
    return data


def distribution(c, study_id, entity_id, variable_id, filters, bin_spec=None):
    body = {"filters": filters, "valueSpec": "count"}
    if bin_spec:
        body["binSpec"] = bin_spec
    return c.post(f"/studies/{study_id}/entities/{entity_id}/variables/{variable_id}/distribution", body)


def compute_status(c, plugin, body, start):
    """autostart=false is a pure lookup (never starts work); true starts or reuses the job."""
    return c.post(f"/computes/{plugin}", body, params={"autostart": "true" if start else "false"})


def job_status(c, job_id):
    return c.get(f"/jobs/{job_id}")


def delete_job(c, job_id):
    c.delete(f"/jobs/{job_id}")


def wait_for_job(c, plugin, body, timeout_s=900, sleep=time.sleep, log=None):
    """Start (or reuse) the job and poll until it leaves queued/in-progress."""
    log = log or (lambda msg: print(msg, file=sys.stderr))
    st = compute_status(c, plugin, body, start=True)
    delay, waited = 2.0, 0.0
    while st["status"] in RUNNING:
        if waited >= timeout_s:
            raise EdaError(
                f"job {st['jobID']} still {st['status']} after {int(waited)}s; it keeps running "
                "server-side: re-run later, or raise --timeout"
            )
        log(f"job {st['jobID']}: {st['status']} ({int(waited)}s)")
        sleep(delay)
        waited += delay
        delay = min(delay * 1.5, 30.0)
        st = job_status(c, st["jobID"])
    return st


def volcano(c, body):
    """The request the WSF plugin makes: all genes' statistics for a completed DE job."""
    return c.post(
        "/apps/differentialexpression/visualizations/volcanoplot",
        {"studyId": body["studyId"], "filters": body["filters"], "computeConfig": body["config"], "config": {}},
    )


def compute_file(c, plugin, body, name):
    """Job output as text. These endpoints answer 406 to Accept: application/json."""
    return c.post(f"/computes/{plugin}/{name}", body, headers={"Accept": "*/*"})
