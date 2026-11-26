from contextlib import asynccontextmanager
from threading import Lock, RLock

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import text, update
from sqlalchemy.exc import IntegrityError
from starlette.staticfiles import StaticFiles

from app import analysis, auth, catalog, design, jobs, prices, projects, system, versions
from app.config import Settings
from app.db import make_engine, make_sessions
from app.middleware import RequestGuard
from app.models import Backup


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    engine = make_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        with app.state.sessions() as session:
            catalog.seed_catalog(session)
            session.execute(update(Backup).where(Backup.status == "running")
                            .values(status="failed", error="服务重启，备份已中断，可重新创建。"))
            session.commit()
        scheduler = jobs.Scheduler(settings, app.state.sessions, app.state.write_lock)
        app.state.scheduler = scheduler
        if settings.worker_enabled:
            scheduler.thread.start()
        try:
            yield
        finally:
            scheduler.stop.set()
            if settings.worker_enabled:
                scheduler.thread.join()
            engine.dispose()

    app = FastAPI(
        title="Forma AI", version="1.0.0", lifespan=lifespan, docs_url=None, redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessions = make_sessions(engine)
    app.state.write_lock = RLock()
    app.state.backup_lock = Lock()
    app.add_middleware(RequestGuard)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        fields = ["未知字段" if item["type"] == "extra_forbidden" else
                  (".".join(map(str, item["loc"][1:])) or "输入") for item in exc.errors()[:8]]
        return JSONResponse({"detail": "请检查字段格式或长度 · " + "、".join(fields)}, status_code=422)

    @app.exception_handler(IntegrityError)
    async def conflict(_: Request, __: IntegrityError):
        return JSONResponse({"detail": "数据已变更或存在重复项，请刷新后重试"}, status_code=409)

    @app.get("/api/health")
    def health():
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok", "version": "1.0.0"}

    for router in (auth.router, auth.admin_router, projects.router, catalog.router, catalog.management,
                   design.router, jobs.router, versions.router, analysis.router, prices.router, system.router):
        app.include_router(router, prefix="/api")

    if (settings.web_dir / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=settings.web_dir / "assets"), name="web-assets")

    @app.get("/{page:path}", include_in_schema=False)
    def spa(page: str, request: Request):
        if page == "api" or page.startswith("api/"):
            raise HTTPException(404, "接口不存在")
        if page in {"forma-product.webp", "forma-mark.png"} and (settings.web_dir / page).is_file():
            return FileResponse(settings.web_dir / page)
        if (settings.web_dir / "index.html").is_file() and (
            not page or "text/html" in request.headers.get("Accept", "")
        ):
            return FileResponse(settings.web_dir / "index.html", headers={"Cache-Control": "no-cache"})
        raise HTTPException(404, "页面不存在")

    return app


app = create_app()
