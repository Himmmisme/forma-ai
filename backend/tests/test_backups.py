import io
import json
from contextlib import contextmanager
from dataclasses import replace
from uuid import uuid4
from zipfile import ZipFile

import pytest
from conftest import PASSWORD, WRITE, add_user
from fastapi.testclient import TestClient
from sqlalchemy import make_url
from sqlalchemy.schema import CreateSchema, DropSchema
from test_costs import completed_version, price_payload
from test_design import design_payload

from app.backups import BackupError, restore_snapshot
from app.db import make_engine, migrate
from app.main import create_app
from app.models import User


@contextmanager
def empty_target(settings, folder):
    folder.mkdir()
    root = None
    if settings.database_url.startswith("postgres"):
        schema = "test_restore_" + uuid4().hex
        url = make_url(settings.database_url)
        root = make_engine(url.difference_update_query(["options"]).render_as_string(hide_password=False))
        with root.begin() as connection:
            connection.execute(CreateSchema(schema))
        dsn = url.update_query_dict({"options": f"-csearch_path={schema}"}).render_as_string(hide_password=False)
    else:
        dsn = f"sqlite:///{(folder / 'restored.sqlite3').as_posix()}"
    target = replace(settings, database_url=dsn, data_dir=folder / "data", secret_dir=folder / "secrets")
    engine = make_engine(dsn)
    try:
        migrate(engine)
        yield engine, target
    finally:
        engine.dispose()
        if root:
            with root.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True))
            root.dispose()


def test_full_restore_preserves_business_data_and_separates_key(owner, application, settings, tmp_path):
    project, vid = completed_version(owner, application)
    data = owner.get(f"/api/versions/{vid}").json()
    assert owner.post("/api/admin/prices", json=price_payload()).status_code == 201
    assert owner.post(f"/api/versions/{vid}/materials", json={
        "name": "已确认选型", "data": {"components": [{"name": "面盖", "material": "ABS"}]},
    }).status_code == 201
    assert owner.post(f"/api/versions/{vid}/costs", json={
        "name": "报价快照", "parts": [{"name": "面盖", "material": "ABS", "weight_kg": ".1"}],
    }).status_code == 201
    provider = owner.post("/api/admin/providers", json={
        "name": "恢复测试", "protocol": "openai", "api_key": "mock-credential-for-recovery",
    }).json()
    queued = owner.post(f"/api/projects/{project}/generate", json=design_payload(
        owner, project, data["originals"][0]["id"], request_key="backup-queued-iteration", parent_id=vid,
    )).json()
    assert owner.put("/api/admin/system", json={"external_enabled": False}).status_code == 200
    blocked = owner.post(f"/api/admin/providers/{provider['id']}/test", json={
        "ack_external": True, "request_key": "system-disabled-api-test",
    })
    assert blocked.status_code == 423
    other, _ = add_user(owner, application)
    assert other.get("/api/admin/backups").status_code == 403
    response = owner.post("/api/admin/backups")
    assert response.status_code == 201 and response.json()["status"] == "succeeded", response.text
    downloaded = owner.get(f"/api/admin/backups/{response.json()['id']}/download")
    with ZipFile(io.BytesIO(downloaded.content)) as bundle:
        manifest = json.loads(bundle.read("manifest.json"))
        assert data["asset"]["id"] in "".join(bundle.namelist())
        assert "login_sessions" not in manifest["tables"]
        assert all("provider.key" not in name for name in bundle.namelist())
        assert b"mock-credential-for-recovery" not in bundle.read("manifest.json")
    assert owner.get("/api/admin/audit").json()["items"][0]["action"] == "backup.created"
    assert owner.get("/api/admin/calls").json()["items"][0]["operation"] == "mock.generate"
    bundle = tmp_path / "snapshot.zip"
    bundle.write_bytes(downloaded.content)
    with empty_target(settings, tmp_path / "restore") as (engine, target):
        restore_snapshot(engine, target, bundle, settings.secret_dir / "provider.key")
        with pytest.raises(BackupError, match="空实例"):
            restore_snapshot(engine, target, bundle)
        with TestClient(create_app(target), headers=WRITE, cookies=dict(owner.cookies)) as client:
            assert client.get("/api/auth/me").status_code == 401
            assert client.post("/api/auth/login", json={"username": "owner", "password": PASSWORD}).status_code == 200
            assert len(client.get(f"/api/projects/{project}/versions").json()["items"]) == 4
            restored = client.get(f"/api/versions/{vid}/analysis").json()
            assert restored["materials"][0]["name"] == "已确认选型"
            assert restored["costs"][0]["name"] == "报价快照"
            assert client.get(f"/api/assets/{data['asset']['id']}/content").content == owner.get(
                f"/api/assets/{data['asset']['id']}/content"
            ).content
            assert client.get(f"/api/jobs/{queued['id']}").json()["status"] == "failed"
            assert client.get("/api/admin/system").json()["external_enabled"] is False
        assert (target.secret_dir / "provider.key").read_bytes() == (settings.secret_dir / "provider.key").read_bytes()


def test_restore_rejects_invalid_members_and_rolls_back_changed_images(owner, application, settings, tmp_path):
    completed_version(owner, application)
    result = owner.post("/api/admin/backups").json()
    zipped = owner.get(f"/api/admin/backups/{result['id']}/download").content
    invalid = tmp_path / "invalid.zip"
    with ZipFile(io.BytesIO(zipped)) as source:
        for invalid_path in (True, False):
            with ZipFile(invalid, "w") as tampered:
                for name in source.namelist():
                    data = source.read(name)
                    if name.startswith("images/") and not invalid_path:
                        data = bytes([data[0] ^ 1]) + data[1:]
                    tampered.writestr(name, data)
                if invalid_path:
                    tampered.writestr("../invalid", b"")
            with empty_target(settings, tmp_path / ("path-test" if invalid_path else "checksum-test")) as (engine, target):
                with pytest.raises(BackupError):
                    restore_snapshot(engine, target, invalid)
                with engine.connect() as connection:
                    assert connection.execute(User.__table__.select()).first() is None
                assert not [file for file in target.data_dir.rglob("*") if file.is_file()]
