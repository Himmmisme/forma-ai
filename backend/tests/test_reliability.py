from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from time import monotonic, sleep

from conftest import WRITE
from fastapi.testclient import TestClient
from test_design import design_payload, new_project

from app.main import create_app
from app.models import Job, utcnow


def test_parallel_submissions_collapse_to_one_job(owner, application):
    project, original = new_project(owner)
    payload = design_payload(owner, project, original)
    path = f"/api/projects/{project}/generate"
    cookies = dict(owner.cookies)

    def request():
        with TestClient(application, headers=WRITE, cookies=cookies) as client:
            return client.post(path, json=payload)

    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(lambda _: request(), range(4)))
    assert all(row.status_code == 202 for row in rows)
    assert len({row.json()["id"] for row in rows}) == 1
    assert len(owner.get(f"/api/projects/{project}/versions").json()["items"]) == 2


def test_queue_recovers_persisted_work_and_interruption(owner, application, settings):
    project, original = new_project(owner)
    path = f"/api/projects/{project}/generate"
    interrupted = owner.post(path, json=design_payload(owner, project, original)).json()
    queued = owner.post(path, json=design_payload(owner, project, original, request_key="forma-restart-task-2")).json()
    with application.state.sessions.begin() as db:
        row = db.get(Job, interrupted["id"])
        row.status = "running"
        row.lease_until = utcnow() - timedelta(seconds=2)

    restarted = create_app(replace(settings, worker_enabled=True))
    with TestClient(restarted, cookies=dict(owner.cookies), headers=WRITE) as client:
        until = monotonic() + 8
        while monotonic() < until:
            done = client.get(f"/api/jobs/{queued['id']}").json()
            if done["status"] in {"failed", "succeeded"}:
                break
            sleep(.15)
        assert done["status"] == "succeeded", done
        lost = client.get(f"/api/jobs/{interrupted['id']}").json()
        assert lost["status"] == "failed" and "中断" in lost["error"]
        asset_id = done["result"]["assets"][0]["id"]
        assert client.get(f"/api/assets/{asset_id}/content").status_code == 200
