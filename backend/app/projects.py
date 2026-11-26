from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import member
from app.core import Input, audit, database, fail, json_fields
from app.models import Asset, DesignVersion, Job, Project, User, utcnow
from app.storage import UPLOAD_LIMIT, asset_path, store_image

router = APIRouter(tags=["项目与素材"])
ASSET_FIELDS = ("id", "project_id", "kind", "filename", "mime", "width", "height", "size", "created_at")
PROJECT_FIELDS = ("id", "name", "description", "cover_id", "favorite", "archived", "deleted_at", "demo",
                  "created_at", "updated_at")


class ProjectCreate(Input):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=4000)


class ProjectUpdate(Input):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=4000)
    cover_id: str | None = Field(default=None, max_length=32)
    favorite: bool | None = None
    archived: bool | None = None


def project_for(
    db: Session, user: User, project_id: str, *, include_deleted: bool = False, lock: bool = False
) -> Project:
    query = select(Project).where(Project.id == project_id, Project.owner_id == user.id)
    if not include_deleted:
        query = query.where(Project.deleted_at.is_(None))
    if lock:
        query = query.with_for_update(key_share=True)
    project = db.scalar(query)
    if not project:
        fail(404, "项目不存在")
    return project


def asset_for(db: Session, user: User, asset_id: str) -> Asset:
    asset = db.scalar(
        select(Asset).join(Project)
        .where(Asset.id == asset_id, Project.owner_id == user.id, Project.deleted_at.is_(None))
    )
    if not asset:
        fail(404, "图片不存在")
    return asset


def project_view(project: Project, version_count: int):
    return {**json_fields(project, *PROJECT_FIELDS), "version_count": version_count}


def asset_view(asset: Asset):
    return json_fields(asset, *ASSET_FIELDS)


def counted_projects():
    counts = (
        select(DesignVersion.project_id.label("project_id"), func.count().label("total"))
        .where(DesignVersion.asset_id.is_not(None)).group_by(DesignVersion.project_id).subquery()
    )
    return select(Project, func.coalesce(counts.c.total, 0)).outerjoin(counts, counts.c.project_id == Project.id)


def count_versions(db: Session, project_id: str) -> int:
    return db.scalar(select(func.count()).select_from(DesignVersion).where(
        DesignVersion.project_id == project_id, DesignVersion.asset_id.is_not(None)
    ))


@router.get("/dashboard")
def dashboard(db: Session = Depends(database), user: User = Depends(member)):
    active = (Project.owner_id == user.id, Project.deleted_at.is_(None), Project.archived.is_(False))
    recent = db.execute(counted_projects().where(*active).order_by(
        Project.favorite.desc(), Project.updated_at.desc(), Project.id
    ).limit(6))
    return {
        "projects": db.scalar(select(func.count()).select_from(Project).where(*active)),
        "versions": db.scalar(select(func.count()).select_from(DesignVersion).join(Project).where(
            Project.owner_id == user.id, Project.deleted_at.is_(None), DesignVersion.asset_id.is_not(None)
        )),
        "running": db.scalar(select(func.count()).select_from(Job).join(Project).where(
            Project.owner_id == user.id, Project.deleted_at.is_(None), Job.status.in_(["queued", "running"])
        )),
        "recent": [project_view(project, count) for project, count in recent],
    }


@router.get("/projects")
def projects(
    status: Literal["active", "archived", "trash", "all"] = "active",
    q: Annotated[str, Query(max_length=120)] = "",
    favorite: bool = False,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 48,
    db: Session = Depends(database),
    user: User = Depends(member),
):
    query = counted_projects().where(Project.owner_id == user.id)
    if status == "trash":
        query = query.where(Project.deleted_at.is_not(None))
    else:
        query = query.where(Project.deleted_at.is_(None))
        if status != "all":
            query = query.where(Project.archived == (status == "archived"))
    if q.strip():
        pattern = "%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        query = query.where(Project.name.ilike(pattern, escape="\\") | Project.description.ilike(pattern, escape="\\"))
    if favorite:
        query = query.where(Project.favorite)
    rows = db.execute(
        query.order_by(Project.favorite.desc(), Project.updated_at.desc(), Project.id).offset(offset).limit(limit + 1)
    ).all()
    return {"items": [project_view(row, count) for row, count in rows[:limit]], "more": len(rows) > limit}


@router.post("/projects", status_code=201)
def create_project(body: ProjectCreate, db: Session = Depends(database), user: User = Depends(member)):
    project = Project(owner_id=user.id, **body.model_dump())
    db.add(project)
    db.commit()
    return project_view(project, 0)


@router.post("/projects/demo")
def demo_project(request: Request, db: Session = Depends(database), user: User = Depends(member)):
    with request.app.state.write_lock:
        db.get(User, user.id, with_for_update=True)
        existing = db.scalar(select(Project).where(
            Project.owner_id == user.id, Project.demo, Project.deleted_at.is_(None), Project.archived.is_(False)
        ).order_by(Project.created_at).limit(1))
        if existing:
            return project_view(existing, count_versions(db, existing.id))
        settings = request.app.state.settings
        if not settings.demo_image.is_file():
            fail(503, "示例素材暂不可用")
        project = Project(
            owner_id=user.id, name="桌面空气净化器", description="原创示例 · 探索外壳比例、CMF 与装配分件。",
            demo=True,
        )
        db.add(project)
        db.flush()
        asset = store_image(settings.data_dir, project.id, "original", "Forma AI 净化器概念.webp",
                            settings.demo_image.read_bytes(), preserve=True)
        try:
            db.add(asset)
            project.cover_id = asset.id
            db.commit()
        except Exception:
            asset_path(settings.data_dir, asset.id).unlink(missing_ok=True)
            raise
    return project_view(project, 0)


@router.get("/projects/{project_id}")
def get_project(project_id: str, db: Session = Depends(database), user: User = Depends(member)):
    project = project_for(db, user, project_id)
    return project_view(project, count_versions(db, project.id))


@router.patch("/projects/{project_id}")
def edit_project(project_id: str, body: ProjectUpdate, db: Session = Depends(database), user: User = Depends(member)):
    project = project_for(db, user, project_id, lock=True)
    values = body.model_dump(exclude_unset=True)
    if "cover_id" in values and values["cover_id"] is not None:
        cover = db.get(Asset, values["cover_id"])
        if not cover or cover.project_id != project.id or cover.deleted_at:
            fail(422, "请从本项目选择封面图片")
    for field, value in values.items():
        if value is not None or field == "cover_id":
            setattr(project, field, value)
    db.commit()
    return project_view(project, count_versions(db, project.id))


@router.delete("/projects/{project_id}", status_code=204)
def trash_project(project_id: str, db: Session = Depends(database), user: User = Depends(member)):
    project = project_for(db, user, project_id, lock=True)
    if db.scalar(select(Job.id).where(Job.project_id == project.id, Job.status.in_(["queued", "running"])).limit(1)):
        fail(409, "请等待此项目的任务完成后移入回收站")
    project.deleted_at = utcnow()
    audit(db, user, "project.trashed", project.id)
    db.commit()


@router.post("/projects/{project_id}/restore")
def restore_project(project_id: str, db: Session = Depends(database), user: User = Depends(member)):
    project = project_for(db, user, project_id, include_deleted=True, lock=True)
    project.deleted_at = None
    audit(db, user, "project.restored", project.id)
    db.commit()
    return project_view(project, count_versions(db, project.id))


@router.get("/projects/{project_id}/assets")
def list_assets(project_id: str, db: Session = Depends(database), user: User = Depends(member)):
    project_for(db, user, project_id)
    return [asset_view(asset) for asset in db.scalars(
        select(Asset).where(Asset.project_id == project_id, Asset.deleted_at.is_(None))
        .order_by(Asset.created_at, Asset.id)
    )]


@router.post("/projects/{project_id}/assets", status_code=201)
def upload_asset(
    project_id: str,
    request: Request,
    file: Annotated[UploadFile, File()],
    kind: Literal["original", "reference", "cover"] = "original",
    db: Session = Depends(database),
    user: User = Depends(member),
):
    data = file.file.read(UPLOAD_LIMIT + 1)
    project = project_for(db, user, project_id, lock=True)
    if project.archived:
        fail(409, "请先取消项目归档")
    data_dir = request.app.state.settings.data_dir
    asset = store_image(data_dir, project_id, kind, file.filename, data)
    try:
        db.add(asset)
        if (not project.cover_id and kind == "original") or kind == "cover":
            project.cover_id = asset.id
        project.updated_at = utcnow()
        db.commit()
    except Exception:
        asset_path(data_dir, asset.id).unlink(missing_ok=True)
        raise
    return asset_view(asset)


@router.delete("/assets/{asset_id}", status_code=204)
def delete_asset(asset_id: str, db: Session = Depends(database), user: User = Depends(member)):
    asset = asset_for(db, user, asset_id)
    project = project_for(db, user, asset.project_id, lock=True)
    if asset.kind == "result":
        fail(409, "成果图片保存在设计版本中")
    if project.archived:
        fail(409, "请先取消项目归档")
    asset.deleted_at = utcnow()
    if project.cover_id == asset.id:
        project.cover_id = None
    project.updated_at = utcnow()
    db.commit()


@router.get("/assets/{asset_id}/content")
def get_asset(
    asset_id: str, request: Request, download: bool = False,
    db: Session = Depends(database), user: User = Depends(member),
):
    asset = asset_for(db, user, asset_id)
    path = asset_path(request.app.state.settings.data_dir, asset.id)
    if not path.is_file():
        fail(404, "图片文件缺失")
    return FileResponse(
        path, media_type=asset.mime, filename=asset.filename,
        content_disposition_type="attachment" if download else "inline",
    )
