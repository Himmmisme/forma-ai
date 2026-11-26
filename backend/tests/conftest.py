import os
import secrets
from dataclasses import replace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import make_url
from sqlalchemy.schema import CreateSchema, DropSchema

from app.config import Settings
from app.db import make_engine, migrate
from app.main import create_app

WRITE = {"X-Forma-Action": "1"}
PASSWORD = "integration-only-1"
CHANGED = "integration-only-2"


@pytest.fixture
def settings(tmp_path):
    url = os.environ.get("FORMA_TEST_DATABASE_URL")
    db_admin = make_engine(url) if url else None
    schema = "test_" + uuid4().hex
    if db_admin:
        with db_admin.begin() as connection:
            connection.execute(CreateSchema(schema))
        db_url = make_url(url).update_query_dict({"options": f"-csearch_path={schema}"}).render_as_string(
            hide_password=False
        )
    else:
        db_url = f"sqlite:///{(tmp_path / 'test.sqlite3').as_posix()}"
    settings = replace(
        Settings.from_env(), database_url=db_url, data_dir=tmp_path / "data", secret_dir=tmp_path / "secrets",
        setup_token=secrets.token_urlsafe(32), worker_enabled=False,
    )
    engine = make_engine(db_url)
    try:
        migrate(engine)
        engine.dispose()
        yield settings
    finally:
        if db_admin:
            with db_admin.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True))
            db_admin.dispose()


@pytest.fixture
def application(settings):
    return create_app(settings)


@pytest.fixture
def owner(application, settings):
    with TestClient(application, headers=WRITE) as client:
        response = client.post("/api/auth/setup", json={
            "username": "owner", "password": PASSWORD, "name": "设计主管", "token": settings.setup_token,
        })
        assert response.status_code == 201, response.text
        yield client


def add_user(client, app, username="designer", role="user"):
    response = client.post("/api/admin/users", json={
        "username": username, "password": PASSWORD, "name": username, "role": role,
    })
    assert response.status_code == 201, response.text
    other = TestClient(app, headers=WRITE)
    assert other.post("/api/auth/login", json={"username": username, "password": PASSWORD}).status_code == 200
    assert other.get("/api/projects").status_code == 403
    assert other.post("/api/auth/password", json={"current_password": PASSWORD, "password": CHANGED}).status_code == 200
    return other, response.json()["id"]
