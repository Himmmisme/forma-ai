import json
import tempfile
from pathlib import Path
from zipfile import ZipFile

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app.auth import member
from app.core import Input, database, fail, json_fields
from app.jobs import job_view, log_rows
from app.models import Asset, CostPlan, DesignVersion, Job, MaterialPlan, Project, User
from app.projects import asset_view, count_versions, project_for, project_view
from app.storage import asset_path, safe_filename

router = APIRouter(tags=["版本与导出"])
VERSION_FIELDS = ("id", "project_id", "user_id", "parent_id", "job_id", "number", "favorite", "created_at")


class Favorite(Input):
    favorite: bool


def version_for(db: Session, user: User, version_id: str, *, ready: bool = False):
    row = db.execute(
        select(DesignVersion, Job, Project).join(Job, Job.id == DesignVersion.job_id)
        .join(Project, Project.id == DesignVersion.project_id)
        .where(DesignVersion.id == version_id, Project.owner_id == user.id, Project.deleted_at.is_(None))
    ).first()
    if not row:
        fail(404, "设计版本不存在")
    if ready and not row[0].asset_id:
        fail(409, "版本成果尚未生成")
    return row


def version_view(version, job, asset):
    config = job.inputs
    return {
        **json_fields(version, *VERSION_FIELDS),
        "status": job.status, "mock": config["provider"]["protocol"] == "mock",
        "asset": asset_view(asset) if asset else None, "direction": config["templates"]["main"]["name"],
        "level": config["templates"]["level"]["name"], "model_name": config["model"]["name"],
    }


def rows_for_versions():
    return (select(DesignVersion, Job, Asset).join(Job, Job.id == DesignVersion.job_id)
            .outerjoin(Asset, Asset.id == DesignVersion.asset_id))


@router.get("/projects/{project_id}/versions")
def list_versions(project_id: str, offset: int = Query(0, ge=0), limit: int = Query(24, ge=1, le=100),
                  db: Session = Depends(database), user: User = Depends(member)):
    project_for(db, user, project_id)
    rows = db.execute(rows_for_versions().where(DesignVersion.project_id == project_id)
                      .order_by(DesignVersion.number.desc()).offset(offset).limit(limit + 1)).all()
    return {"items": [version_view(*row) for row in rows[:limit]], "more": len(rows) > limit}


@router.get("/versions/{version_id}")
def version_details(version_id: str, db: Session = Depends(database), user: User = Depends(member)):
    version, job, project = version_for(db, user, version_id)
    assets = {asset.id: asset_view(asset) for asset in db.scalars(select(Asset).where(
        Asset.project_id == project.id, Asset.id.in_([*job.inputs["asset_ids"], version.asset_id])
    ))}
    parent = db.get(DesignVersion, version.parent_id) if version.parent_id else None
    return {
        **version_view(version, job, db.get(Asset, version.asset_id) if version.asset_id else None),
        "project_name": project.name, "author": db.get(User, version.user_id).name,
        "parent_number": parent.number if parent else None,
        "configuration": job.inputs,
        "originals": [assets[identifier] for identifier in job.inputs["originals"]],
        "references": [assets[identifier] for identifier in job.inputs["references"]],
        "iteration": assets.get(job.inputs["iteration"]),
        "job": job_view(job, log_rows(db, job.id)),
    }


@router.patch("/versions/{version_id}")
def favorite_version(version_id: str, body: Favorite, db: Session = Depends(database), user: User = Depends(member)):
    version, job, _ = version_for(db, user, version_id, ready=True)
    version.favorite = body.favorite
    db.commit()
    return version_view(version, job, db.get(Asset, version.asset_id))


@router.get("/favorites")
def favorite_versions(offset: int = Query(0, ge=0), limit: int = Query(24, ge=1, le=100),
                      db: Session = Depends(database), user: User = Depends(member)):
    rows = db.execute(rows_for_versions().add_columns(Project.name).join(Project, Project.id == DesignVersion.project_id)
                      .where(Project.owner_id == user.id, Project.deleted_at.is_(None), DesignVersion.favorite,
                             DesignVersion.asset_id.is_not(None))
                      .order_by(DesignVersion.created_at.desc(), DesignVersion.id).offset(offset).limit(limit + 1)).all()
    return {"items": [{**version_view(version, job, asset), "project_name": name}
                      for version, job, asset, name in rows[:limit]], "more": len(rows) > limit}


@router.get("/projects/{project_id}/comparison-options")
def comparison_options(project_id: str, db: Session = Depends(database), user: User = Depends(member)):
    project_for(db, user, project_id)
    originals = list(db.scalars(select(Asset).where(Asset.project_id == project_id, Asset.kind == "original")
                               .order_by(Asset.created_at, Asset.id)))
    versions = db.execute(select(DesignVersion, Asset).join(Asset, Asset.id == DesignVersion.asset_id)
                          .where(DesignVersion.project_id == project_id).order_by(DesignVersion.number.desc())).all()
    return (
        [{"id": asset.id, "label": f"原图 · {asset.filename}" + ("（已移除）" if asset.deleted_at else ""),
          "asset": asset_view(asset)} for asset in originals]
        + [{"id": version.id, "label": f"V{version.number:03d}", "asset": asset_view(asset)} for version, asset in versions]
    )


def exported_plans(db: Session, table, version_ids, extra):
    return [json_fields(row, "id", "version_id", "user_id", "name", "data", "created_at", "updated_at", extra)
            for row in db.scalars(select(table).where(table.version_id.in_(version_ids)))]


@router.get("/projects/{project_id}/export")
def export_project(project_id: str, request: Request, db: Session = Depends(database), user: User = Depends(member)):
    project = project_for(db, user, project_id, lock=True)
    all_jobs = list(db.scalars(select(Job).where(Job.project_id == project.id).order_by(Job.created_at)))
    if any(job.status in {"queued", "running"} for job in all_jobs):
        fail(409, "项目仍有任务正在执行，请在任务结束后导出完整成果")
    versions = db.execute(rows_for_versions().where(DesignVersion.project_id == project.id)
                          .order_by(DesignVersion.number)).all()
    snapshots = [
        {**job_view(job, log_rows(db, job.id)), "configuration": job.inputs}
        for job in all_jobs
    ]
    version_ids = [row[0].id for row in versions]
    assets = list(db.scalars(select(Asset).where(Asset.project_id == project.id).order_by(Asset.created_at)))
    payload = {
        "format": "forma-project-v1", "project": project_view(project, count_versions(db, project.id)),
        "owner": {"id": user.id, "name": user.name}, "versions": [version_view(*row) for row in versions],
        "jobs": snapshots, "assets": [
            {**asset_view(asset), **json_fields(asset, "sha256", "deleted_at"), "file": f"images/{asset.id}/{asset.filename}"}
            for asset in assets
        ],
        "materials": exported_plans(db, MaterialPlan, version_ids, "job_id"),
        "costs": exported_plans(db, CostPlan, version_ids, "material_plan_id"),
    }
    with tempfile.NamedTemporaryFile(prefix="forma-project-", suffix=".zip", delete=False) as temp:
        output = Path(temp.name)
    data_dir = request.app.state.settings.data_dir
    try:
        with ZipFile(output, "w") as archive:
            archive.writestr("project.json", json.dumps(payload, ensure_ascii=False, indent=2))
            for asset in assets:
                source = asset_path(data_dir, asset.id)
                if not source.is_file():
                    fail(409, "项目存在缺失的图片文件，请检查实例存储")
                archive.write(source, f"images/{asset.id}/{asset.filename}")
    except Exception:
        output.unlink(missing_ok=True)
        raise
    return FileResponse(output, filename=f"{safe_filename(project.name, 'forma-project')}.zip",
                        media_type="application/zip", background=BackgroundTask(output.unlink, missing_ok=True))
