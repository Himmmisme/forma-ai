import io
import json
from zipfile import ZipFile

from conftest import add_user
from test_design import design_payload, execute_queued, new_project

from app.models import Job
from app.storage import asset_path


def test_each_image_branches_and_retains_snapshot(owner, application):
    project, original = new_project(owner)
    path = f"/api/projects/{project}"
    payload = design_payload(owner, project, original)
    parent_job = owner.post(path + "/generate", json=payload).json()
    execute_queued(application)
    root_ids = owner.get(f"/api/jobs/{parent_job['id']}").json()["result"]["version_ids"]
    parent = owner.get(f"/api/versions/{root_ids[1]}").json()
    assert parent["number"] == 2 and parent["parent_id"] is None
    assert owner.delete(f"/api/assets/{original}").status_code == 204
    old_template = parent["configuration"]["templates"]["main"]
    edited = owner.put(f"/api/admin/templates/{old_template['id']}", json={
        **{key: old_template[key] for key in ("name", "summary", "sort", "enabled")}, "body": "改用统一的表面纹理",
    })
    assert edited.status_code == 200
    for index in (1, 2):
        result = owner.post(path + "/generate", json={
            **payload, "request_key": f"forma-branch-test-{index}", "parent_id": parent["id"], "originals": [],
            "output": {**payload["output"], "count": 1},
        })
        assert result.status_code == 202, result.text
        execute_queued(application)
    versions = owner.get(path + "/versions").json()["items"]
    assert [item["number"] for item in versions] == [4, 3, 2, 1]
    assert [item["parent_id"] for item in versions] == [parent["id"], parent["id"], None, None]
    child = owner.get(f"/api/versions/{versions[0]['id']}").json()
    assert child["parent_number"] == 2 and child["iteration"]["id"] == parent["asset"]["id"]
    assert child["originals"][0]["id"] == original
    assert child["configuration"]["templates"]["main"]["revision"] == old_template["revision"] + 1
    assert owner.get(f"/api/versions/{parent['id']}").json()["configuration"] == parent["configuration"]
    assert len(owner.get(path + "/comparison-options").json()) == 5
    assert owner.patch(f"/api/versions/{child['id']}", json={"favorite": True}).status_code == 200
    assert owner.get("/api/favorites").json()["items"][0]["id"] == child["id"]
    archive = owner.get(path + "/export")
    assert archive.status_code == 200
    with ZipFile(io.BytesIO(archive.content)) as bundle:
        exported = json.loads(bundle.read("project.json"))
        assert len(exported["versions"]) == 4
        assert len(exported["assets"]) == 5
        assert exported["jobs"][0]["configuration"]["prompt"]
        for asset in exported["assets"]:
            assert bundle.read(asset["file"])
    other, _ = add_user(owner, application)
    assert other.get(path + "/export").status_code == 404
    assert other.get(f"/api/versions/{child['id']}").status_code == 404
    assert other.get(f"/api/jobs/{parent_job['id']}").status_code == 404
    assert not other.get("/api/favorites").json()["items"]


def test_failed_job_retry_preserves_reserved_version(owner, application, settings):
    project, original = new_project(owner)
    path = f"/api/projects/{project}"
    payload = design_payload(owner, project, original)
    queued = owner.post(path + "/generate", json=payload).json()
    source = asset_path(settings.data_dir, original)
    content = source.read_bytes()
    source.unlink()
    execute_queued(application)
    assert owner.get(f"/api/jobs/{queued['id']}").json()["status"] == "failed"
    saved = owner.get(path + "/versions").json()["items"]
    assert all(item["status"] == "failed" and not item["asset"] for item in saved)
    source.write_bytes(content)
    retry = owner.post(f"/api/jobs/{queued['id']}/retry", json={}).json()
    assert retry["generation"] == 2
    assert owner.post(f"/api/jobs/{queued['id']}/retry", json={}).json()["generation"] == 2
    execute_queued(application)
    assert [item["id"] for item in owner.get(path + "/versions").json()["items"]] == [item["id"] for item in saved]
    with application.state.sessions() as db:
        assert db.get(Job, retry["id"]).status == "succeeded"
