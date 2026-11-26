from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import member
from app.catalog import choose_model
from app.core import Input, database, fail, json_fields
from app.costing import CostInput, calculate
from app.design import input_limits
from app.jobs import JobRequest, enqueue, existing_job, fingerprint, job_view
from app.material_schema import MATERIAL_PROMPT, MaterialData
from app.models import Asset, CostPlan, Job, MaterialPlan, User
from app.projects import project_for
from app.versions import version_for

router = APIRouter(prefix="/versions/{version_id}", tags=["材料和成本"])
PLAN_FIELDS = ("id", "version_id", "user_id", "name", "data", "created_at", "updated_at")


class AnalyzeInput(JobRequest):
    kind: Literal["materials", "manufacturing", "cost_advice"] = "materials"
    notes: str = Field(default="", max_length=2000)


class MaterialInput(Input):
    name: str = Field(min_length=1, max_length=120)
    data: MaterialData
    job_id: str | None = Field(default=None, max_length=32)


@router.get("/analysis")
def list_analysis(version_id: str, db: Session = Depends(database), user: User = Depends(member)):
    version_for(db, user, version_id, ready=True)
    material = db.scalars(select(MaterialPlan).where(MaterialPlan.version_id == version_id)
                          .order_by(MaterialPlan.updated_at.desc(), MaterialPlan.id)).all()
    costs = db.scalars(select(CostPlan).where(CostPlan.version_id == version_id)
                       .order_by(CostPlan.updated_at.desc(), CostPlan.id)).all()
    jobs = db.scalars(select(Job).where(Job.user_id == user.id, Job.inputs["version_id"].as_string() == version_id,
                                      Job.kind.in_(["materials", "manufacturing", "cost_advice"]))
                      .order_by(Job.created_at.desc(), Job.id).limit(25)).all()
    return {"materials": [json_fields(row, *PLAN_FIELDS, "job_id") for row in material],
            "costs": [json_fields(row, *PLAN_FIELDS, "material_plan_id") for row in costs],
            "jobs": [job_view(row) for row in jobs]}


@router.post("/analysis", status_code=202)
def submit_analysis(version_id: str, body: AnalyzeInput, request: Request,
                    db: Session = Depends(database), user: User = Depends(member)):
    with request.app.state.write_lock:
        db.get(User, user.id, with_for_update=True)
        version, _, project = version_for(db, user, version_id, ready=True)
        project = project_for(db, user, project.id, lock=True)
        digest = fingerprint(body, version=version.id)
        job = existing_job(db, user, body.kind, body.request_key, digest)
        if not job:
            if project.archived:
                fail(409, "请先取消项目归档")
            photo = db.get(Asset, version.asset_id)
            model, provider = choose_model(db, body.kind)
            input_limits([photo], model, provider)
            options = {
                "materials": MATERIAL_PROMPT,
                "manufacturing": "分析可见分件的制造工艺、拔模或折弯、表面处理、装配与维护。说明需要验证的边界。",
                "cost_advice": "分析可见部件的成本驱动、可能的降本策略和待确认的数据。不要计算或猜测最终金额。",
            }
            prompt = options[body.kind]
            if body.kind != "materials":
                prompt += "输出中文 JSON 对象，字段 summary（字符串）和 uncertainties（字符串数组）。"
            if body.notes:
                prompt += "\n用户补充要求：" + body.notes
            job = enqueue(db, user, project, body.kind, body, digest, model, provider, {
                "version_id": version.id, "asset_ids": [photo.id], "prompt": prompt, "notes": body.notes,
            })
            db.commit()
        return job_view(job)


def material_for(db, version_id, plan_id):
    row = db.get(MaterialPlan, plan_id)
    if not row or row.version_id != version_id:
        fail(404, "材料方案不存在")
    return row


def save_material(db, user, version_id, body, plan_id=None):
    version, _, project = version_for(db, user, version_id, ready=True)
    project_for(db, user, project.id, lock=True)
    row = material_for(db, version_id, plan_id) if plan_id else MaterialPlan(version_id=version.id, user_id=user.id)
    if body.job_id:
        job = db.get(Job, body.job_id)
        if (not job or job.user_id != user.id or job.kind != "materials" or job.status != "succeeded"
                or job.inputs.get("version_id") != version.id):
            fail(422, "选型任务不属于此版本或尚未成功")
    row.name, row.data, row.job_id = body.name, body.data.model_dump(mode="json"), body.job_id
    db.add(row)
    db.commit()
    return json_fields(row, *PLAN_FIELDS, "job_id")


@router.post("/materials", status_code=201)
def create_material(version_id: str, body: MaterialInput, db: Session = Depends(database), user: User = Depends(member)):
    return save_material(db, user, version_id, body)


@router.put("/materials/{plan_id}")
def update_material(version_id: str, plan_id: str, body: MaterialInput,
                    db: Session = Depends(database), user: User = Depends(member)):
    return save_material(db, user, version_id, body, plan_id)


@router.post("/costs/calculate")
def preview_cost(version_id: str, body: CostInput, db: Session = Depends(database), user: User = Depends(member)):
    version_for(db, user, version_id, ready=True)
    if body.material_plan_id:
        material_for(db, version_id, body.material_plan_id)
    return calculate(db, body)


def save_cost(db, user, version_id, body, plan_id=None):
    version, _, project = version_for(db, user, version_id, ready=True)
    project_for(db, user, project.id, lock=True)
    if body.material_plan_id:
        material_for(db, version_id, body.material_plan_id)
    row = CostPlan(version_id=version.id, user_id=user.id) if not plan_id else db.get(CostPlan, plan_id)
    if not row or row.version_id != version_id:
        fail(404, "成本方案不存在")
    row.name, row.material_plan_id = body.name, body.material_plan_id
    row.data = {"inputs": body.model_dump(mode="json"), "result": calculate(db, body)}
    db.add(row)
    db.commit()
    return json_fields(row, *PLAN_FIELDS, "material_plan_id")


@router.post("/costs", status_code=201)
def create_cost(version_id: str, body: CostInput, db: Session = Depends(database), user: User = Depends(member)):
    return save_cost(db, user, version_id, body)


@router.put("/costs/{plan_id}")
def update_cost(version_id: str, plan_id: str, body: CostInput,
                db: Session = Depends(database), user: User = Depends(member)):
    return save_cost(db, user, version_id, body, plan_id)
