from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from alembic import command


def make_engine(url: str) -> Engine:
    sqlite = url.startswith("sqlite")
    engine = create_engine(
        url,
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={"check_same_thread": False, "timeout": 20} if sqlite else {"connect_timeout": 8},
    )
    if sqlite:
        @event.listens_for(engine, "connect")
        def configure_sqlite(connection, _):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    return engine


def make_sessions(engine: Engine):
    return sessionmaker(engine, expire_on_commit=False)


def migrate(engine: Engine):
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
