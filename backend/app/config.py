import os
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import URL

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    database_url: str
    data_dir: Path
    secret_dir: Path
    web_dir: Path
    demo_image: Path
    setup_token: str = field(default="", repr=False)
    cookie_secure: bool = False
    worker_enabled: bool = True
    worker_slots: int = 4

    @classmethod
    def from_env(cls) -> "Settings":
        data = Path(os.getenv("APP_DATA_DIR", str(ROOT / ".runtime" / "data"))).resolve()
        web = Path(os.getenv("APP_WEB_DIR", str(ROOT / "frontend" / "dist"))).resolve()
        database_url = os.getenv("DATABASE_URL")
        if not database_url and (host := os.getenv("APP_DB_HOST")):
            database_url = URL.create(
                "postgresql+psycopg", username=os.getenv("APP_DB_USER", "forma"),
                password=os.getenv("APP_DB_PASSWORD"), host=host, port=5432,
                database=os.getenv("APP_DB_NAME", "forma"),
            ).render_as_string(hide_password=False)
        return cls(
            database_url=database_url or f"sqlite:///{(data / 'forma.sqlite3').as_posix()}",
            data_dir=data,
            secret_dir=Path(os.getenv("APP_SECRET_DIR", str(ROOT / ".runtime" / "secrets"))).resolve(),
            web_dir=web,
            demo_image=Path(
                os.getenv("APP_DEMO_IMAGE", str(ROOT / "frontend" / "public" / "forma-product.webp"))
            ).resolve(),
            setup_token=os.getenv("APP_SETUP_TOKEN", ""),
            cookie_secure=os.getenv("APP_COOKIE_SECURE", "0") == "1",
            worker_enabled=os.getenv("APP_WORKER_ENABLED", "1") == "1",
            worker_slots=max(1, min(8, int(os.getenv("APP_WORKER_SLOTS", "4")))),
        )
