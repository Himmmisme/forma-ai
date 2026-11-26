import asyncio
import json

from sqlalchemy import select
from test_accounts_projects import png

from app.adapters import CompatibleAdapter, GeminiAdapter, ImageInput, OpenAIAdapter
from app.models import Job, Provider
from app.transport import public_ip, unseal


def design_payload(owner, project, asset, **extra):
    templates = {row["slug"]: row["id"] for row in owner.get("/api/design/catalog").json()["templates"]}
    return {
        "request_key": "forma-integration-original", "originals": [asset], "references": [],
        "main": templates["cmf"], "level": templates["l3"], "raw": "改为深绿哑光",
        "constraints": "保留接口", "output": {"count": 2, "ratio": "3:2", "size": "1536x1024"}, **extra,
    }


def new_project(owner):
    project = owner.post("/api/projects", json={"name": "空气净化器"}).json()
    asset = owner.post(f"/api/projects/{project['id']}/assets", files={"file": ("source.png", png(), "image/png")})
    assert asset.status_code == 201, asset.text
    return project["id"], asset.json()["id"]


def execute_queued(app):
    queue = app.state.scheduler
    claim = queue.claim()
    assert claim is not None
    queue.execute(*claim)
    return claim[0]


def test_mock_pipeline_and_idempotency(owner, application):
    project, image = new_project(owner)
    path = f"/api/projects/{project}"
    payload = design_payload(owner, project, image)
    preview = owner.post(path + "/preview", json={k: v for k, v in payload.items() if k != "request_key"})
    assert preview.status_code == 200
    assert "保留接口" in preview.json()["prompt"]
    response = owner.post(path + "/generate", json=payload)
    assert response.status_code == 202, response.text
    queued = response.json()
    assert queued["status"] == "queued"
    assert owner.post(path + "/generate", json=payload).json()["id"] == queued["id"]
    assert owner.post(path + "/generate", json={**payload, "raw": "不同需求"}).status_code == 409
    assert execute_queued(application) == queued["id"]
    job = owner.get(f"/api/jobs/{queued['id']}").json()
    assert job["status"] == "succeeded", job
    assert len(job["result"]["version_ids"]) == len(job["result"]["assets"]) == 2
    assert job["calls"][0]["operation"] == "mock.generate"
    asset = job["result"]["assets"][0]
    assert (asset["width"], asset["height"]) == (1536, 1024)
    assert owner.get(f"/api/assets/{asset['id']}/content").status_code == 200
    assert owner.post(f"/api/jobs/{job['id']}/retry", json={}).status_code == 409


def test_optimize_preserves_inputs_and_requires_conflict_confirmation(owner, application):
    project, image = new_project(owner)
    path = f"/api/projects/{project}"
    request = design_payload(owner, project, image, raw="保留接口，并移除接口")
    assert owner.post(path + "/generate", json=request).status_code == 422
    optimized = owner.post(path + "/optimize", json={
        "request_key": "forma-optimization-key", "raw": request["raw"], "constraints": request["constraints"],
    })
    assert optimized.status_code == 202, optimized.text
    result = owner.get(f"/api/jobs/{execute_queued(application)}").json()["result"]
    assert request["raw"] in result["optimized"]
    assert result["conflicts"]


def test_provider_encryption_safe_response_and_mock_probe(owner, application, settings):
    payload = {"name": "兼容测试", "protocol": "compatible", "api_key": "local-test-secret",
               "base_url": "https://127.0.0.1/v1"}
    assert owner.post("/api/admin/providers", json=payload).status_code == 422
    safe = owner.post("/api/admin/providers", json={**payload, "base_url": "https://api.example.com/v1"})
    assert safe.status_code == 201, safe.text
    assert safe.json()["has_key"] and payload["api_key"] not in safe.text
    with application.state.sessions() as db:
        stored = db.get(Provider, safe.json()["id"]).key_encrypted
        assert stored != payload["api_key"]
        assert unseal(settings.secret_dir, stored) == payload["api_key"]
    assert payload["api_key"] not in owner.get("/api/admin/catalog").text
    assert owner.post(f"/api/admin/providers/{safe.json()['id']}/test", json={
        "request_key": "forma-provider-connect",
    }).status_code == 422
    mock = next(row for row in owner.get("/api/admin/catalog").json()["providers"] if row["protocol"] == "mock")
    probe = owner.post(f"/api/admin/providers/{mock['id']}/test", json={"request_key": "forma-mock-provider-key"})
    assert probe.status_code == 202
    assert execute_queued(application) == probe.json()["id"]
    with application.state.sessions() as db:
        assert db.scalar(select(Job.status).where(Job.id == probe.json()["id"])) == "succeeded"


class Stub:
    def __init__(self):
        self.requests = []
        self.responses = []

    async def request(self, method, path, **params):
        self.requests.append((method, path, params))
        return json.dumps(self.responses.pop(0)).encode(), 200, "request_test"

    def start(self, operation):
        return operation

    def finish(self, *_):
        pass


def test_official_request_shapes_use_documented_paths():
    http = Stub()
    http.responses = [
        {"output": [{"type": "message", "content": [{"type": "output_text", "text": "ok"}]}]},
        {"data": [{"b64_json": "YQ=="}]},
        {"choices": [{"message": {"content": "ok"}}]},
        {"candidates": [{"content": {"parts": [{"inlineData": {"data": "Yg=="}}]}}]},
    ]
    image = ImageInput("image/png", b"image bytes")
    output = {"ratio": "1:1", "size": "1024x1024", "count": 1}
    openai = OpenAIAdapter("https://api.openai.com/v1", "test", 5, http, http)
    assert asyncio.run(openai.text("test-text", "prompt", [image])) == "ok"
    assert asyncio.run(openai.images("test-image", "prompt", [image, image], output)) == [b"a"]
    compatible = CompatibleAdapter("https://api.example.com/v1", "test", 5, http, http)
    assert asyncio.run(compatible.text("test-text", "prompt", [image])) == "ok"
    gemini = GeminiAdapter("https://generativelanguage.googleapis.com/v1beta", "test", 5, http, http)
    assert asyncio.run(gemini.images("gemini-test", "prompt", [image], {**output, "size": "2K"})) == [b"b"]
    assert http.requests[0][1].endswith("/responses")
    assert http.requests[0][2]["json"]["input"][0]["content"][1]["type"] == "input_image"
    assert http.requests[1][1].endswith("/images/edits")
    assert [row[0] for row in http.requests[1][2]["files"]] == ["image[]", "image[]"]
    assert http.requests[2][1].endswith("/chat/completions")
    assert http.requests[3][1].endswith("/models/gemini-test:generateContent")
    assert http.requests[3][2]["headers"] == {"x-goog-api-key": "test"}
    assert http.requests[3][2]["json"]["generationConfig"]["imageConfig"] == {"aspectRatio": "1:1", "imageSize": "2K"}


def test_network_address_filter():
    for address in ("127.0.0.1", "10.0.0.1", "169.254.169.254", "224.0.0.1", "::1", "::ffff:127.0.0.1"):
        assert not public_ip(address)
    assert public_ip("8.8.8.8")
