from dataclasses import replace

from fastapi.testclient import TestClient
from sqlalchemy import inspect

from app.config import Settings
from app.db import make_engine, migrate
from app.main import create_app
from app.models import Base


def test_migration_matches_application_tables(tmp_path):
    settings = replace(
        Settings.from_env(),
        database_url=f"sqlite:///{(tmp_path / 'forma.sqlite3').as_posix()}",
        data_dir=tmp_path,
        worker_enabled=False,
    )
    engine = make_engine(settings.database_url)
    try:
        migrate(engine)
        migrate(engine)
        assert set(inspect(engine).get_table_names()) == set(Base.metadata.tables) | {"alembic_version"}
    finally:
        engine.dispose()
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/health").json()["status"] == "ok"
        assert client.get("/api/missing").status_code == 404
