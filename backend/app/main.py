from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import text
from starlette.staticfiles import StaticFiles

from app.config import Settings
from app.db import make_engine, make_sessions


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    engine = make_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        yield
        engine.dispose()

    app = FastAPI(title="Forma AI", version="1.0.0", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessions = make_sessions(engine)

    @app.get("/api/health")
    def health():
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok", "version": "1.0.0"}

    if (settings.web_dir / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=settings.web_dir / "assets"), name="web-assets")

    @app.get("/{page:path}", include_in_schema=False)
    def spa(page: str, request: Request):
        if page == "api" or page.startswith("api/"):
            raise HTTPException(404, "接口不存在")
        if page in {"forma-product.webp", "forma-mark.png"} and (settings.web_dir / page).is_file():
            return FileResponse(settings.web_dir / page)
        if (settings.web_dir / "index.html").is_file() and "text/html" in request.headers.get("Accept", ""):
            return FileResponse(settings.web_dir / "index.html", headers={"Cache-Control": "no-cache"})
        raise HTTPException(404, "页面不存在")

    return app


app = create_app()
