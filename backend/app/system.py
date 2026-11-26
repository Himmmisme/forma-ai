from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import superadmin
from app.backups import BackupError, create_snapshot
from app.catalog import external_enabled
from app.core import Input, audit, database, fail, json_fields
from app.jobs import CALL_FIELDS
from app.models import AuditEvent, Backup, CallLog, Job, Provider, Setting, User

router = APIRouter(prefix="/admin", tags=["系统"])
BACKUP_FIELDS = ("id", "status", "size", "error", "created_at")


class SystemInput(Input):
    external_enabled: bool


def backup_path(data_dir: Path, identifier: str):
    return data_dir / "backups" / f"forma-{identifier}.zip"


@router.get("/system")
def system_settings(request: Request, db: Session = Depends(database), _: User = Depends(superadmin)):
    return {"external_enabled": external_enabled(db), "worker_slots": request.app.state.settings.worker_slots}


@router.put("/system")
def save_settings(body: SystemInput, db: Session = Depends(database), actor: User = Depends(superadmin)):
    db.get(Setting, "bootstrap", with_for_update=True)
    db.merge(Setting(key="runtime", value=body.model_dump()))
    audit(db, actor, "system.settings_saved", external_enabled=body.external_enabled)
    db.commit()
    return body.model_dump()


@router.get("/audit")
def audit_log(offset: int = Query(0, ge=0), db: Session = Depends(database), _: User = Depends(superadmin)):
    entries = db.execute(select(AuditEvent, User.name).outerjoin(User, User.id == AuditEvent.user_id)
                         .order_by(AuditEvent.created_at.desc(), AuditEvent.id).offset(offset).limit(101)).all()
    return {"items": [{**json_fields(event, "id", "action", "entity_id", "context", "created_at"),
                      "actor": name} for event, name in entries[:100]], "more": len(entries) > 100}


@router.get("/calls")
def api_log(offset: int = Query(0, ge=0), db: Session = Depends(database), _: User = Depends(superadmin)):
    entries = db.execute(
        select(CallLog, Job.kind, Provider.name).join(Job, Job.id == CallLog.job_id)
        .join(Provider, Provider.id == Job.provider_id).order_by(CallLog.created_at.desc(), CallLog.id)
        .offset(offset).limit(101)
    ).all()
    return {"items": [{**json_fields(row, *CALL_FIELDS, "job_id"), "kind": kind, "provider": name}
                      for row, kind, name in entries[:100]], "more": len(entries) > 100}


@router.get("/backups")
def list_backups(offset: int = Query(0, ge=0), db: Session = Depends(database), _: User = Depends(superadmin)):
    rows = db.scalars(select(Backup).order_by(Backup.created_at.desc(), Backup.id).offset(offset).limit(51)).all()
    return {"items": [json_fields(row, *BACKUP_FIELDS) for row in rows[:50]], "more": len(rows) > 50}


@router.post("/backups", status_code=201)
def create_backup(request: Request, db: Session = Depends(database), actor: User = Depends(superadmin)):
    lock = request.app.state.backup_lock
    if not lock.acquire(blocking=False):
        fail(409, "已有备份正在执行")
    try:
        row = Backup(user_id=actor.id, status="running")
        db.add(row)
        db.commit()
        destination = backup_path(request.app.state.settings.data_dir, row.id)
        try:
            row.size = create_snapshot(request.app.state.engine, request.app.state.settings.data_dir, destination)
            row.status = "succeeded"
        except BackupError as error:
            row.status, row.error = "failed", str(error)
        except Exception:
            row.status, row.error = "failed", "备份执行失败，请检查数据库与存储状态"
        audit(db, actor, "backup.created", row.id, status=row.status)
        db.commit()
        return json_fields(row, *BACKUP_FIELDS)
    finally:
        lock.release()


@router.get("/backups/{identifier}/download")
def download_backup(identifier: str, request: Request, db: Session = Depends(database), _: User = Depends(superadmin)):
    row = db.get(Backup, identifier)
    if not row or row.status != "succeeded":
        fail(404, "备份不存在或未完成")
    file = backup_path(request.app.state.settings.data_dir, row.id)
    if not file.is_file():
        fail(404, "备份文件不存在")
    return FileResponse(file, filename=file.name, media_type="application/zip")
