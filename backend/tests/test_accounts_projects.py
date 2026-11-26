import io

from conftest import CHANGED, PASSWORD, WRITE, add_user
from fastapi.testclient import TestClient
from PIL import Image


def png():
    buffer = io.BytesIO()
    Image.new("RGB", (160, 100), "#628868").save(buffer, "PNG")
    return buffer.getvalue()


def test_bootstrap_requires_token_and_csrf(application, settings):
    with TestClient(application) as guest:
        data = {"username": "Owner", "name": "工作室", "password": PASSWORD, "token": "wrong"}
        assert guest.get("/api/projects").status_code == 401
        assert guest.post("/api/auth/setup", json=data).status_code == 403
        assert guest.post("/api/auth/setup", json=data, headers=WRITE).status_code == 403
        data["token"] = settings.setup_token
        response = guest.post("/api/auth/setup", json=data, headers=WRITE)
        assert response.status_code == 201
        assert response.json()["username"] == "owner"
        assert "httponly" in response.headers["set-cookie"].lower()
        assert "samesite=strict" in response.headers["set-cookie"].lower()
        assert guest.post("/api/auth/setup", json=data, headers=WRITE).status_code == 409
        assert guest.post("/api/auth/logout", headers=WRITE).status_code == 204
        assert guest.get("/api/auth/me").status_code == 401


def test_project_image_storage_and_isolation(owner, application):
    designer, _ = add_user(owner, application)
    response = designer.post("/api/projects", json={"name": "传感器_100%", "description": "初代"})
    assert response.status_code == 201
    project_id = response.json()["id"]
    assert owner.get(f"/api/projects/{project_id}").status_code == 404
    assert owner.patch(f"/api/projects/{project_id}", json={"favorite": True}).status_code == 404
    assert owner.get(f"/api/projects/{project_id}/assets").status_code == 404
    assert not owner.get("/api/projects").json()["items"]
    assert designer.get("/api/projects", params={"q": "_100%"}).json()["items"][0]["id"] == project_id
    route = f"/api/projects/{project_id}/assets"
    assert designer.post(route, files={"file": ("fake.png", b"<svg>", "image/png")}).status_code == 415
    result = designer.post(route, files={"file": ("../../orig.png", png(), "image/png")})
    assert result.status_code == 201
    image = result.json()
    assert image["width"] == 160 and "/" not in image["filename"]
    content = f"/api/assets/{image['id']}/content"
    assert owner.get(content).status_code == 404
    assert designer.get(content).headers["content-type"] == "image/webp"
    assert "attachment" in designer.get(content, params={"download": True}).headers["content-disposition"]
    assert designer.get(f"/api/projects/{project_id}").json()["cover_id"] == image["id"]
    assert designer.patch(f"/api/projects/{project_id}", json={"archived": True}).status_code == 200
    assert designer.post(route, files={"file": ("orig.png", png(), "image/png")}).status_code == 409
    assert designer.delete(f"/api/projects/{project_id}").status_code == 204
    assert designer.get(content).status_code == 404
    assert designer.post(f"/api/projects/{project_id}/restore").status_code == 200
    assert designer.get(content).status_code == 200


def test_admin_scope_and_reset_revokes_sessions(owner, application):
    administrator, admin_id = add_user(owner, application, "workspace-admin", "admin")
    designer, designer_id = add_user(owner, application)
    assert administrator.get("/api/admin/users").json()[0]["id"] == designer_id
    assert designer.get("/api/admin/users").status_code == 403
    assert administrator.patch(f"/api/admin/users/{admin_id}", json={"enabled": False}).status_code == 404
    assert administrator.patch(f"/api/admin/users/{designer_id}", json={"role": "admin"}).status_code == 403
    assert administrator.post(f"/api/admin/users/{designer_id}/password", json={"password": PASSWORD}).status_code == 204
    assert designer.get("/api/auth/me").status_code == 401
    assert designer.post("/api/auth/login", json={"username": "designer", "password": CHANGED}).status_code == 401
    assert designer.post("/api/auth/login", json={"username": "designer", "password": PASSWORD}).status_code == 200
    assert designer.get("/api/projects").status_code == 403
