from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import member
from app.catalog import choose_model
from app.core import Input, database, fail
from app.jobs import JobRequest, enqueue, existing_job, fingerprint, job_view
from app.models import Asset, DesignVersion, Job, User, utcnow
from app.projects import project_for
from app.prompts import BASE_REVISION, compose, conflict_hints, get_templates, template_view

router = APIRouter(prefix="/projects/{project_id}", tags=["设计工作台"])


class Output(Input):
    count: int = Field(default=1, ge=1, le=4)
    ratio: str = Field(max_length=8)
    size: str = Field(max_length=32)
    background: Literal["studio", "white", "dark", "context"] = "studio"
    view: Literal["three_quarter", "front", "side", "top"] = "three_quarter"


class DesignInput(Input):
    originals: list[str] = Field(default_factory=list, max_length=16)
    references: list[str] = Field(default_factory=list, max_length=16)
    parent_id: str | None = Field(default=None, max_length=32)
    main: str = Field(max_length=32)
    auxiliary: list[str] = Field(default_factory=list, max_length=5)
    level: str = Field(max_length=32)
    raw: str = Field(default="", max_length=3500)
    optimized: str = Field(default="", max_length=6000)
    final: str = Field(default="", max_length=6000)
    constraints: str = Field(default="", max_length=1800)
    model_id: str | None = Field(default=None, max_length=32)
    output: Output


class GenerateInput(DesignInput, JobRequest):
    ack_conflicts: bool = False


class OptimizeInput(JobRequest):
    raw: str = Field(min_length=1, max_length=3500)
    constraints: str = Field(default="", max_length=1800)
    main: str | None = Field(default=None, max_length=32)
    level: str | None = Field(default=None, max_length=32)


class InspectInput(JobRequest):
    originals: list[str] = Field(min_length=1, max_length=16)


def selected_assets(db, project_id, ids, kind, historic=()):
    if len(ids) != len(set(ids)) or any(len(item) != 32 for item in ids):
        fail(422, "图片选择重复或标识无效")
    rows = {asset.id: asset for asset in db.scalars(select(Asset).where(
        Asset.project_id == project_id, Asset.kind == kind, Asset.id.in_(ids)
    )) if not asset.deleted_at or asset.id in historic}
    if len(rows) != len(ids):
        fail(422, "所选图片不属于此项目、类型不符或已移除")
    return [rows[item] for item in ids]


def input_limits(images, model, provider):
    if len(images) > model.max_inputs or len(images) > 1 and "multi_image" not in model.capabilities:
        fail(422, f"该模型最多支持 {model.max_inputs} 张输入图，请调整选择")
    megabytes = 14 if provider.protocol == "gemini" else 32
    if provider.protocol != "mock" and sum(row.size for row in images) > megabytes * 1024 * 1024:
        fail(422, f"输入图片总大小超过 {megabytes} MB，请减少图片")


def prepare_design(db: Session, project_id: str, body: DesignInput):
    task = "edit" if body.parent_id else "generate"
    model, provider = choose_model(db, task, body.model_id)
    output = body.output.model_dump()
    if output["count"] > model.max_count or not any(
        spec["ratio"] == output["ratio"] and spec["value"] == output["size"] for spec in model.sizes
    ):
        fail(422, "生成数量、比例或分辨率超出所选模型的配置")
    iteration = None
    inherited = {}
    if body.parent_id:
        parent = db.get(DesignVersion, body.parent_id)
        if not parent or parent.project_id != project_id or not parent.asset_id:
            fail(404, "父版本不存在或没有可用成果")
        iteration = db.get(Asset, parent.asset_id)
        inherited = db.get(Job, parent.job_id).inputs
    originals = selected_assets(
        db, project_id, body.originals or inherited.get("originals", []), "original", inherited.get("originals", [])
    )
    if not originals:
        fail(422, "请选入至少一张产品原图")
    references = selected_assets(db, project_id, body.references, "reference", inherited.get("references", []))
    all_assets = ([iteration] if iteration else []) + originals + references
    input_limits(all_assets, model, provider)
    directions = get_templates(db, [body.main, *body.auxiliary], "direction")
    level = get_templates(db, [body.level], "level")[0]
    warnings = conflict_hints(body.raw, body.final or body.optimized, body.constraints, level.slug, directions, references)
    prompt = compose(
        original=originals, references=references, iteration=iteration, directions=directions, level=level,
        raw=body.raw, optimized=body.optimized, final=body.final, constraints=body.constraints, output=output,
    )
    payload = {
        "parent_id": body.parent_id, "iteration": iteration.id if iteration else None,
        "originals": [asset.id for asset in originals], "references": [asset.id for asset in references],
        "asset_ids": [asset.id for asset in all_assets], "raw": body.raw, "optimized": body.optimized,
        "final": body.final or body.optimized or body.raw, "constraints": body.constraints, "prompt": prompt,
        "templates": {"base_revision": BASE_REVISION, "main": template_view(directions[0]),
                      "auxiliary": [template_view(template) for template in directions[1:]], "level": template_view(level)},
        "output": output, "warnings": warnings,
    }
    return task, model, provider, payload


@router.post("/preview")
def preview(project_id: str, body: DesignInput, db: Session = Depends(database), user: User = Depends(member)):
    project_for(db, user, project_id)
    _, _, provider, payload = prepare_design(db, project_id, body)
    return {"prompt": payload["prompt"], "warnings": payload["warnings"], "mock": provider.protocol == "mock"}


@router.post("/generate", status_code=202)
def generate(project_id: str, body: GenerateInput, request: Request,
             db: Session = Depends(database), user: User = Depends(member)):
    with request.app.state.write_lock:
        db.get(User, user.id, with_for_update=True, populate_existing=True)
        project = project_for(db, user, project_id, lock=True)
        task = "edit" if body.parent_id else "generate"
        digest = fingerprint(body, project=project_id)
        job = existing_job(db, user, task, body.request_key, digest)
        if job:
            return job_view(job)
        if project.archived:
            fail(409, "请先取消项目归档")
        _, model, provider, payload = prepare_design(db, project_id, body)
        if payload["warnings"] and not body.ack_conflicts:
            fail(422, "当前提示词有潜在冲突，请先预览并确认")
        job = enqueue(db, user, project, task, body, digest, model, provider, payload)
        for index in range(body.output.count):
            db.add(DesignVersion(
                project_id=project_id, user_id=user.id, job_id=job.id, parent_id=body.parent_id,
                number=project.next_version + index, output_index=index,
            ))
        project.next_version += body.output.count
        project.updated_at = utcnow()
        db.commit()
        return job_view(job)


@router.post("/optimize", status_code=202)
def optimize(project_id: str, body: OptimizeInput, request: Request,
             db: Session = Depends(database), user: User = Depends(member)):
    with request.app.state.write_lock:
        db.get(User, user.id, with_for_update=True)
        project = project_for(db, user, project_id, lock=True)
        digest = fingerprint(body, project=project_id)
        job = existing_job(db, user, "optimize", body.request_key, digest)
        if not job:
            if project.archived:
                fail(409, "请先取消项目归档")
            main = get_templates(db, [body.main], "direction") if body.main else []
            level = get_templates(db, [body.level], "level")[0] if body.level else None
            warning = conflict_hints(body.raw, body.raw, body.constraints, level.slug if level else "", main, [])
            model, provider = choose_model(db, "optimize")
            prompt = (
                "将以下用户输入整理成中文工业设计提示词。按设计目标、必须保留、执行约束、输出要求分组。"
                "忠实保留每条意图。遇到未知内容标待确认，禁止新增未请求的功能、结构变更或规格。"
                "保留约束优先，指出原文冲突。只输出 JSON 对象，字段 optimized（字符串）和 conflicts（字符串数组）。\n"
                f"方向：{main[0].name if main else '未指定'}。档位：{level.name if level else '未指定'}。\n"
                f"原始需求：{body.raw}\n必须保留：{body.constraints}"
            )
            job = enqueue(db, user, project, "optimize", body, digest, model, provider, {
                "raw": body.raw, "constraints": body.constraints, "prompt": prompt, "warnings": warning,
            })
            db.commit()
        return job_view(job)


@router.post("/inspect", status_code=202)
def inspect_originals(project_id: str, body: InspectInput, request: Request,
                      db: Session = Depends(database), user: User = Depends(member)):
    with request.app.state.write_lock:
        db.get(User, user.id, with_for_update=True)
        project = project_for(db, user, project_id, lock=True)
        digest = fingerprint(body, project=project_id)
        job = existing_job(db, user, "inspect", body.request_key, digest)
        if not job:
            if project.archived:
                fail(409, "请先取消项目归档")
            images = selected_assets(db, project_id, body.originals, "original")
            model, provider = choose_model(db, "inspect")
            input_limits(images, model, provider)
            job = enqueue(db, user, project, "inspect", body, digest, model, provider, {
                "asset_ids": body.originals,
                "prompt": "以工业设计师视角记录图中可见的整体比例、分件、交互区和维护边界。所有不可见信息列待确认。"
                          "返回中文 JSON 对象，字段 summary（字符串）和 uncertainties（字符串数组）。",
            })
            db.commit()
        return job_view(job)
