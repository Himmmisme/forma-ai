import asyncio
import base64
import json

import pytest
from httpx import AsyncClient, ByteStream, Headers, MockTransport, Response
from sqlalchemy import select
from test_accounts_projects import png

from app.adapters import VX_BASE_URL, CompatibleAdapter, GeminiAdapter, ImageInput, OpenAIAdapter
from app.models import Job, Model, Provider
from app.transport import SafeHTTP, UpstreamError, check_url, pinned_address, public_ip, response_id, unseal


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


def mock_upstream(monkeypatch, respond):
    def stream_response(request):
        return Response(200, stream=ByteStream(json.dumps(respond(request)).encode()))

    def mock_client(**kwargs):
        assert not kwargs["trust_env"] and not kwargs["follow_redirects"]
        return AsyncClient(transport=MockTransport(stream_response), **kwargs)

    monkeypatch.setattr("app.transport.httpx.AsyncClient", mock_client)


def test_local_http_provider_connection_and_generation(owner, application, monkeypatch):
    local_url = "http://127.0.0.1:8080/v1"
    provider = {"name": "本地 HTTP", "protocol": "compatible", "base_url": "http://localhost:8081/v1"}
    for invalid_url in ("http://224.0.0.1:8080/v1", "http://169.254.169.254/v1", local_url + "?key=test",
                        "http://127.0.0.1:65536/v1", "http://user:secret@127.0.0.1:8080/v1"):
        response = owner.post("/api/admin/providers", json={**provider, "base_url": invalid_url})
        assert response.status_code == 422, response.text
    created = owner.post("/api/admin/providers", json=provider)
    assert created.status_code == 201, created.text
    provider_id = created.json()["id"]
    updated = owner.put(f"/api/admin/providers/{provider_id}", json={**provider, "base_url": local_url + "/"})
    assert updated.status_code == 200, updated.text
    assert updated.json()["base_url"] == local_url
    assert not updated.json()["has_key"]

    requests = []

    def respond(request):
        requests.append(request)
        assert request.url.netloc == b"127.0.0.1:8080"
        assert request.headers["Host"] == "127.0.0.1:8080"
        if request.url.path == "/v1/models":
            assert "Authorization" not in request.headers
            return {"data": [{"id": "local-model"}]}
        assert request.url.path == "/v1/images/edits"
        assert request.headers["Authorization"] == "Bearer local-test-key"
        return {"data": [{"b64_json": base64.b64encode(png()).decode("ascii")}]}

    mock_upstream(monkeypatch, respond)
    probe = owner.post(f"/api/admin/providers/{provider_id}/test", json={
        "request_key": "forma-local-connect", "ack_external": True,
    })
    assert probe.status_code == 202, probe.text
    tested = owner.get(f"/api/jobs/{execute_queued(application)}").json()
    assert tested["status"] == "succeeded", tested
    assert tested["result"]["models"] == ["local-model"]

    authenticated = {**provider, "base_url": local_url, "api_key": "local-test-key"}
    assert owner.put(f"/api/admin/providers/{provider_id}", json=authenticated).status_code == 200
    changed = owner.put(f"/api/admin/providers/{provider_id}", json=provider)
    assert changed.status_code == 422
    model = owner.post("/api/admin/models", json={
        "provider_id": provider_id, "name": "本地模型", "model_code": "local-model",
        "capabilities": ["image_generate", "image_edit"],
        "sizes": [{"ratio": "1:1", "label": "方图", "value": "1024x1024"}],
    })
    assert model.status_code == 201, model.text
    project, asset = new_project(owner)
    body = design_payload(owner, project, asset, ack_external=True, model_id=model.json()["id"],
                          output={"count": 1, "ratio": "1:1", "size": "1024x1024"})
    queued = owner.post(f"/api/projects/{project}/generate", json=body)
    assert queued.status_code == 202, queued.text
    completed = owner.get(f"/api/jobs/{execute_queued(application)}").json()
    assert completed["status"] == "succeeded", completed
    assert len(completed["result"]["version_ids"]) == 1
    assert [(request.method, str(request.url)) for request in requests] == [
        ("GET", local_url + "/models"), ("POST", local_url + "/images/edits"),
    ]


def test_custom_gemini_http_provider_uses_native_paths(owner, application, monkeypatch):
    config = {"name": "Gemini 代理", "protocol": "gemini", "api_key": "mock-gemini-key"}
    official = owner.post("/api/admin/providers", json={**config, "name": "Gemini 官方测试"})
    assert official.status_code == 201, official.text
    assert official.json()["base_url"] == "https://generativelanguage.googleapis.com/v1beta"

    origin = "http://8.8.8.8:8080"
    explicit = owner.post("/api/admin/providers", json={**config, "name": "Gemini 显式前缀", "base_url": origin + "/proxy/v1"})
    assert explicit.status_code == 201, explicit.text
    assert explicit.json()["base_url"] == origin + "/proxy/v1"

    provider = owner.post("/api/admin/providers", json={**config, "base_url": origin})
    assert provider.status_code == 201, provider.text
    assert provider.json()["base_url"] == origin + "/v1beta"
    provider_id = provider.json()["id"]
    requests = []

    def respond(request):
        requests.append((request.method, str(request.url)))
        assert request.headers["x-goog-api-key"] == "mock-gemini-key"
        if request.method == "GET":
            return {"models": [{"name": "models/gemini-test"}]}
        assert json.loads(request.content)["contents"][0]["parts"][0]["text"]
        return {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}

    mock_upstream(monkeypatch, respond)
    probe = owner.post(f"/api/admin/providers/{provider_id}/test", json={
        "request_key": "forma-gemini-connect", "ack_external": True,
    })
    assert probe.status_code == 202, probe.text
    tested = owner.get(f"/api/jobs/{execute_queued(application)}").json()
    assert tested["status"] == "succeeded", tested
    assert tested["result"]["models"] == ["models/gemini-test"]

    model = owner.post("/api/admin/models", json={
        "name": "Gemini 测试模型", "provider_id": provider_id, "model_code": "gemini-test", "capabilities": ["text"],
    })
    assert model.status_code == 201, model.text
    model_id = model.json()["id"]
    probe_model = owner.post(f"/api/admin/models/{model_id}/test", json={
        "request_key": "forma-gemini-test", "ack_external": True, "capability": "text",
    })
    assert probe_model.status_code == 202, probe_model.text
    tested_model = owner.get(f"/api/jobs/{execute_queued(application)}").json()
    assert tested_model["status"] == "succeeded", tested_model
    assert requests == [
        ("GET", origin + "/v1beta/models"), ("POST", origin + "/v1beta/models/gemini-test:generateContent"),
    ]


def test_http_provider_dns_and_asset_download_policy(monkeypatch):
    local_url = "http://model.lan:8080/v1"
    public_url = "http://proxy.example.com:8080/v1"
    answers = {"model.lan": ["192.168.1.50"], "proxy.example.com": ["8.8.8.8"]}

    async def check_addresses():
        async def resolve(host, port, **_):
            assert port == 8080
            return [(0, 0, 0, "", (address, port)) for address in answers[host]]

        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolve)
        local = check_url(local_url, allow_http=True)
        public = check_url(public_url, allow_http=True)
        assert await pinned_address(local) == "192.168.1.50"
        assert await pinned_address(public) == "8.8.8.8"
        answers["model.lan"].append("8.8.8.8")
        with pytest.raises(UpstreamError, match="本地域名"):
            await pinned_address(local)
        answers["proxy.example.com"] = ["127.0.0.1"]
        with pytest.raises(UpstreamError, match="公网地址"):
            await pinned_address(public)
        for url in (local_url, public_url):
            with pytest.raises(UpstreamError, match="公网 HTTPS"):
                await SafeHTTP(5).request("GET", url + "/result.png")

    asyncio.run(check_addresses())


class Stub:
    def __init__(self):
        self.requests = []
        self.responses = []

    async def request(self, method, path, **params):
        self.requests.append((method, path, params))
        response = self.responses.pop(0)
        return (response if isinstance(response, bytes) else json.dumps(response).encode()), 200, "request_test"

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


def test_vx_gpt_image_probe_uses_synchronous_generation_and_rejects_failed_results():
    http = Stub()
    http.responses = [
        {"status": "succeeded", "data": [{"b64_json": "YQ=="}]},
        {"data": [{"b64_json": "YQ=="}]},
        {"status": "failed", "failure_reason": "status_code=502, upstream request failed", "data": [{"b64_json": "YQ=="}]},
        {"status": "succeeded", "data": []},
    ]
    adapter = CompatibleAdapter(VX_BASE_URL, "test", 5, http, http)
    model = "gpt-image-2.5-pro"
    output = {"ratio": "1:1", "size": "1024x1024", "count": 1}
    assert asyncio.run(adapter.images(model, "prompt", [], output)) == [b"a"]
    method, url, params = http.requests[0]
    assert (method, url) == ("POST", VX_BASE_URL + "/images/generations")
    assert params["json"] == {"model": model, "prompt": "prompt", "size": "1K", "aspect_ratio": "1:1",
                              "quality": "auto", "stream": False, "async": False}
    with pytest.raises(UpstreamError, match="仅有文生图接口"):
        asyncio.run(adapter.images(model, "prompt", [ImageInput("image/png", b"image bytes")], output))
    assert asyncio.run(adapter.images(model, "prompt", [], output)) == [b"a"]
    with pytest.raises(UpstreamError, match="上游 HTTP 502"):
        asyncio.run(adapter.images(model, "prompt", [], output))
    with pytest.raises(UpstreamError, match="缺少可下载的图片链接"):
        asyncio.run(adapter.images(model, "prompt", [], output))
    assert len(http.requests) == 4


def test_vx_project_generation_uses_single_multipart_image(owner, application, monkeypatch):
    http = Stub()
    result_url = "https://assets.example.com/generated.png"
    http.responses = [{"status": "succeeded", "data": [{"url": result_url}]}, png()]

    async def request(_transport, method, path, **params):
        return await http.request(method, path, **params)

    monkeypatch.setattr(SafeHTTP, "request", request)
    provider = owner.post("/api/admin/providers", json={
        "name": "VX API", "protocol": "compatible", "base_url": VX_BASE_URL, "api_key": "mock-test-key",
    })
    assert provider.status_code == 201, provider.text
    model = {"provider_id": provider.json()["id"], "name": "VX 单图模型",
             "model_code": "gemini-nano-banana-2.1", "capabilities": ["image_generate", "image_edit"],
             "sizes": [{"ratio": "1:1", "label": "1K", "value": "1K"}]}
    created = owner.post("/api/admin/models", json=model)
    assert created.status_code == 201, created.text
    legacy = owner.post("/api/admin/models", json={**model, "name": "VX 文生图",
                        "model_code": "gpt-image-2.5-pro", "capabilities": ["image_generate"]})
    assert legacy.status_code == 201, legacy.text
    legacy_id = legacy.json()["id"]
    with application.state.sessions() as db:
        db.get(Model, legacy_id).capabilities = ["image_generate", "image_edit", "multi_image"]
        db.commit()
    catalog = owner.get("/api/admin/catalog").json()
    assert next(item for item in catalog["models"] if item["id"] == legacy_id)["capabilities"] == ["image_generate"]
    assert owner.put("/api/admin/bindings/generate", json={"model_id": legacy_id}).status_code == 422
    assert owner.put("/api/admin/bindings/edit", json={"model_id": created.json()["id"]}).status_code == 422
    assert owner.put("/api/admin/bindings/generate", json={"model_id": created.json()["id"]}).status_code == 200

    project, asset = new_project(owner)
    body = design_payload(owner, project, asset, ack_external=True,
                          output={"count": 1, "ratio": "1:1", "size": "1K"})
    queued = owner.post(f"/api/projects/{project}/generate", json=body)
    assert queued.status_code == 202, queued.text
    completed = owner.get(f"/api/jobs/{execute_queued(application)}").json()
    assert completed["status"] == "succeeded", completed
    assert len(completed["result"]["version_ids"]) == 1
    method, path, params = http.requests[0]
    assert (method, path) == ("POST", VX_BASE_URL + "/images/edits")
    [(field_name, (filename, image_bytes, mime))] = params["files"]
    assert (field_name, filename, mime) == ("image", "input.png", "image/png")
    assert image_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    assert params["data"]["size"] == "1K"
    assert params["data"]["aspect_ratio"] == "1:1"
    assert http.requests[1][:2] == ("GET", result_url)
    assert "headers" not in http.requests[1][2]


def test_retry_rejects_image_job_when_the_saved_model_no_longer_supports_generation(owner, application, monkeypatch):
    http = Stub()
    http.responses = [{"error": {"message": "upstream test failure"}}]

    async def request(_transport, method, path, **params):
        return await http.request(method, path, **params)

    monkeypatch.setattr(SafeHTTP, "request", request)
    provider = owner.post("/api/admin/providers", json={
        "name": "测试服务商", "protocol": "compatible", "base_url": "https://api.example.com/v1", "api_key": "mock-key",
    })
    assert provider.status_code == 201, provider.text
    model = {"provider_id": provider.json()["id"], "name": "测试模型", "model_code": "demo-model",
             "capabilities": ["image_generate", "image_edit"],
             "sizes": [{"ratio": "1:1", "label": "1024", "value": "1024x1024"}]}
    created = owner.post("/api/admin/models", json=model)
    assert created.status_code == 201, created.text
    model_id = created.json()["id"]
    project, image = new_project(owner)
    body = design_payload(owner, project, image, model_id=model_id, ack_external=True,
                          output={"count": 1, "ratio": "1:1", "size": "1024x1024"})
    queued = owner.post(f"/api/projects/{project}/generate", json=body)
    assert queued.status_code == 202, queued.text
    job_id = execute_queued(application)
    path = f"/api/jobs/{job_id}"
    failed = owner.get(path).json()
    assert failed["status"] == "failed" and failed["model_code"] == "demo-model"
    edited = owner.put(f"/api/admin/models/{model_id}", json={**model, "capabilities": ["text"]})
    assert edited.status_code == 200, edited.text

    retry = owner.post(path + "/retry", json={"ack_external": True})
    assert retry.status_code == 409 and "创建新任务" in retry.json()["detail"]
    assert owner.get(path).json() == failed
    assert len(http.requests) == 1


def test_oneapi_request_id_is_used_when_valid():
    assert response_id(Headers({"x-oneapi-request-id": "gateway-trace_1", "x-request-id": "edge-trace"})) == "gateway-trace_1"
    assert response_id(Headers({"x-oneapi-request-id": "invalid / trace", "x-request-id": "edge-trace"})) == "edge-trace"


def test_network_address_filter():
    for address in ("127.0.0.1", "10.0.0.1", "169.254.169.254", "224.0.0.1", "::1", "::ffff:127.0.0.1"):
        assert not public_ip(address)
    assert public_ip("8.8.8.8")
