import asyncio
import hashlib
import io
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event, Thread
from time import monotonic

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from PIL import Image
from pydantic import Field, ValidationError
from sqlalchemy import func, select, tuple_, update
from sqlalchemy.orm import Session

from app.adapters import ADAPTERS, ImageInput, mock_images, structured
from app.auth import member
from app.catalog import (
    REAL_PROTOCOLS,
    Capability,
    can_serve,
    external_enabled,
    get_model,
    get_provider,
    model_capabilities,
)
from app.core import Input, audit, database, fail, json_fields
from app.material_schema import MOCK_MATERIALS, MaterialData
from app.models import Asset, CallLog, DesignVersion, Job, Model, Provider, User, utcnow
from app.projects import asset_view, project_for
from app.storage import OUTPUT_LIMIT, asset_path, store_image, validate_image
from app.transport import UpstreamError, unseal

router = APIRouter(tags=["任务队列"])
logger = logging.getLogger("forma.jobs")
JOB_FIELDS = ("id", "project_id", "model_id", "provider_id", "kind", "status", "error",
              "generation", "result", "created_at", "updated_at")
CALL_FIELDS = ("id", "generation", "operation", "status", "request_id", "http_status",
               "elapsed_ms", "usage", "created_at")
IMAGE_TASKS = {"generate", "edit"}
ACTIVE = {"queued", "running"}
LEASE_SECONDS = 40
HEARTBEAT_SECONDS = 8


class JobRequest(Input):
    request_key: str = Field(pattern=r"^[a-zA-Z0-9_-]{16,64}$")
    ack_external: bool = False


class RetryInput(Input):
    ack_external: bool = False


class Probe(JobRequest):
    capability: Capability = "text"


class Optimized(Input):
    optimized: str = Field(min_length=1, max_length=6000)
    conflicts: list[str] = Field(default_factory=list, max_length=16)


class Observation(Input):
    summary: str = Field(min_length=1, max_length=8000)
    uncertainties: list[str] = Field(default_factory=list, max_length=24)


def job_view(job: Job, logs: list[CallLog] | None = None):
    return {
        **json_fields(job, *JOB_FIELDS),
        "mock": job.inputs["provider"]["protocol"] == "mock",
        "model_code": (job.inputs.get("model") or {}).get("model_code"),
        **({"calls": [json_fields(row, *CALL_FIELDS) for row in logs]} if logs is not None else {}),
    }


def log_rows(db: Session, job_id: str):
    return list(db.scalars(select(CallLog).where(CallLog.job_id == job_id).order_by(CallLog.created_at, CallLog.id)))


def job_for(db: Session, user: User, job_id: str, *, lock=False):
    query = select(Job).where(Job.id == job_id, Job.user_id == user.id)
    if lock:
        query = query.with_for_update()
    job = db.scalar(query)
    if not job or job.kind.startswith("probe_") and user.role != "superadmin":
        fail(404, "任务不存在")
    if job.project_id:
        project_for(db, user, job.project_id)
    return job


def fingerprint(body: JobRequest, **context):
    values = body.model_dump(mode="json", exclude={"request_key", "ack_external", "ack_conflicts"})
    return hashlib.sha256(json.dumps([context, values], sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def existing_job(db, user, kind, key, digest):
    job = db.scalar(select(Job).where(Job.user_id == user.id, Job.kind == kind, Job.request_key == key))
    if job and job.request_hash != digest:
        fail(409, "该请求标识已用于另一组参数")
    return job


def enqueue(db, user, project, kind, body, digest, model, provider, payload):
    if provider.protocol in REAL_PROTOCOLS:
        if not external_enabled(db):
            fail(423, "系统已暂停外部 API 调用")
        if not body.ack_external:
            fail(422, "请确认外部模型接收相关输入，调用可能产生费用")
    count = db.scalar(select(func.count()).select_from(Job).where(Job.user_id == user.id, Job.status.in_(ACTIVE)))
    if count >= 24:
        fail(429, "当前排队及运行任务较多，请等待后继续")
    job = Job(
        user_id=user.id, project_id=project.id if project else None, model_id=model.id if model else None,
        provider_id=provider.id, kind=kind, request_key=body.request_key, request_hash=digest,
        inputs={
            **payload,
            "provider": json_fields(provider, "id", "name", "protocol", "base_url"),
            "model": {**json_fields(model, "id", "name", "model_code", "pricing"),
                      "capabilities": model_capabilities(model, provider)} if model else None,
        },
    )
    db.add(job)
    db.flush()
    return job


@router.get("/jobs/{job_id}")
def get_job(job_id: str, db: Session = Depends(database), user: User = Depends(member)):
    return job_view(job_for(db, user, job_id), log_rows(db, job_id))


@router.get("/projects/{project_id}/jobs")
def project_jobs(project_id: str, offset: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100),
                 db: Session = Depends(database), user: User = Depends(member)):
    project_for(db, user, project_id)
    return [job_view(job) for job in db.scalars(select(Job).where(Job.project_id == project_id)
              .order_by(Job.created_at.desc(), Job.id).offset(offset).limit(limit))]


@router.post("/jobs/{job_id}/retry", status_code=202)
def retry_job(job_id: str, body: RetryInput, request: Request,
              db: Session = Depends(database), user: User = Depends(member)):
    with request.app.state.write_lock:
        # Acquire the project lock before the job, matching submission and trash operations.
        previous = job_for(db, user, job_id)
        if previous.project_id:
            project = project_for(db, user, previous.project_id, lock=True)
            if project.archived:
                fail(409, "请先取消项目归档")
        db.refresh(previous, with_for_update=True)
        if previous.status in ACTIVE:
            return job_view(previous)
        if previous.status != "failed":
            fail(409, "只有失败的任务可重试")
        if previous.kind in IMAGE_TASKS:
            model = db.get(Model, previous.model_id) if previous.model_id else None
            provider = db.get(Provider, previous.provider_id)
            saved_code = (previous.inputs.get("model") or {}).get("model_code")
            if (not model or not provider or model.model_code != saved_code
                    or provider.base_url != previous.inputs["provider"]["base_url"]
                    or not can_serve(model, provider, previous.kind)):
                fail(409, "原任务的图片模型或服务商配置已失效，请在工作台选择图片模型并创建新任务")
        if previous.inputs["provider"]["protocol"] in REAL_PROTOCOLS and not body.ack_external:
            fail(422, "重试可能再次计费，请确认")
        if previous.inputs["provider"]["protocol"] in REAL_PROTOCOLS and not external_enabled(db):
            fail(423, "系统已暂停外部 API 调用")
        previous.status, previous.error, previous.lease_until = "queued", None, None
        previous.generation += 1
        audit(db, user, "job.retried", previous.id, attempt=previous.generation)
        db.commit()
        return job_view(previous)


@router.post("/admin/providers/{provider_id}/test", status_code=202)
def test_provider(provider_id: str, body: JobRequest, request: Request,
                  db: Session = Depends(database), user: User = Depends(member)):
    if user.role != "superadmin":
        fail(403, "需要超级管理员权限")
    return submit_probe(request, db, user, get_provider(db, provider_id), None, body, "probe_connection")


@router.post("/admin/models/{model_id}/test", status_code=202)
def test_model(model_id: str, body: Probe, request: Request,
               db: Session = Depends(database), user: User = Depends(member)):
    if user.role != "superadmin":
        fail(403, "需要超级管理员权限")
    model, provider = get_model(db, model_id)
    if body.capability not in model_capabilities(model, provider) or not model.enabled:
        fail(422, "该模型未启用或不支持所选能力")
    return submit_probe(request, db, user, provider, model, body, "probe_model")


def submit_probe(request, db, user, provider, model, body, kind):
    with request.app.state.write_lock:
        db.get(User, user.id, with_for_update=True)
        digest = fingerprint(body, provider=provider.id, model=model.id if model else None)
        job = existing_job(db, user, kind, body.request_key, digest)
        if not job:
            if not provider.enabled:
                fail(422, "请先启用服务商")
            payload = {"capability": body.capability, "sizes": model.sizes} if model else {}
            job = enqueue(db, user, None, kind, body, digest, model, provider, payload)
            audit(db, user, "provider.test_queued", provider.id, kind=kind)
            db.commit()
        return job_view(job)


class Calls:
    def __init__(self, sessions, job):
        self.sessions, self.job = sessions, job

    def start(self, operation):
        with self.sessions.begin() as db:
            row = CallLog(job_id=self.job.id, generation=self.job.generation, operation=operation, status="running")
            db.add(row)
            db.flush()
            return row.id, monotonic()

    def finish(self, call, status, http_status=None, request_id=None, usage=None):
        identifier, start = call
        with self.sessions.begin() as db:
            row = db.get(CallLog, identifier)
            row.status = status
            row.http_status, row.request_id, row.usage = http_status, request_id, usage
            row.elapsed_ms = round((monotonic() - start) * 1000)


class Scheduler:
    def __init__(self, settings, sessions, lock):
        self.settings, self.sessions, self.lock = settings, sessions, lock
        self.stop = Event()
        self.thread = Thread(target=self.loop, name="forma-queue", daemon=True)

    def loop(self):
        with ThreadPoolExecutor(max_workers=self.settings.worker_slots, thread_name_prefix="forma-task") as pool:
            pending = {}
            heartbeat_at = monotonic()
            while not self.stop.is_set():
                pending = {key: future for key, future in pending.items() if not future.done()}
                try:
                    if pending and monotonic() >= heartbeat_at:
                        self.heartbeat(list(pending))
                        heartbeat_at = monotonic() + HEARTBEAT_SECONDS
                    if len(pending) < self.settings.worker_slots:
                        if info := self.claim():
                            pending[info] = pool.submit(self.execute, *info)
                            continue
                except Exception:
                    logger.warning("Task queue database unavailable")
                self.stop.wait(.65)

    def heartbeat(self, leases):
        with self.sessions.begin() as db:
            db.execute(update(Job).where(Job.status == "running", tuple_(Job.id, Job.generation).in_(leases))
                       .values(lease_until=utcnow() + timedelta(seconds=LEASE_SECONDS),
                               updated_at=Job.updated_at))

    def claim(self):
        with self.lock, self.sessions.begin() as db:
            now = utcnow()
            stale = list(db.scalars(select(Job).where(
                Job.status == "running", Job.lease_until < now,
            ).with_for_update(skip_locked=True)))
            for job in stale:
                job.status, job.lease_until = "failed", None
                job.error = "执行中断。上游可能已接收请求，请确认后重试。"
                db.execute(update(CallLog).where(CallLog.job_id == job.id, CallLog.status == "running")
                           .values(status="interrupted"))
            # Group by provider so one saturated provider cannot starve other queued jobs.
            providers = db.scalars(select(Provider).where(
                Provider.id.in_(select(Job.provider_id).where(Job.status == "queued"))
            ).order_by(Provider.id).with_for_update(skip_locked=True)).all()
            available = []
            for provider in providers:
                count = db.scalar(select(func.count()).select_from(Job).where(
                    Job.status == "running", Job.provider_id == provider.id
                ))
                if count < provider.concurrency:
                    available.append(provider)
            if not available:
                return None
            job = db.scalar(select(Job).where(Job.status == "queued", Job.provider_id.in_(
                [row.id for row in available]
            )).order_by(Job.created_at, Job.id).limit(1).with_for_update(skip_locked=True))
            if not job:
                return None
            job.status = "running"
            job.lease_until = now + timedelta(seconds=LEASE_SECONDS)
            return job.id, job.generation

    def execute(self, identifier, generation):
        try:
            with self.sessions() as db:
                job = db.get(Job, identifier)
                if not job or job.status != "running" or job.generation != generation:
                    return
                if job.lease_until < utcnow():
                    raise UpstreamError("任务租约已过期，请重试")
                provider = db.get(Provider, job.provider_id)
                model = db.get(Model, job.model_id) if job.model_id else None
                user = db.get(User, job.user_id)
                if not user.enabled or job.kind.startswith("probe_") and user.role != "superadmin":
                    raise UpstreamError("任务创建者的账号或权限已停用")
                if job.project_id:
                    project_for(db, user, job.project_id)
                if not provider.enabled or model and not model.enabled:
                    raise UpstreamError("服务商或模型已停用")
                if provider.protocol in REAL_PROTOCOLS and not external_enabled(db):
                    raise UpstreamError("系统已暂停外部 API 调用")
                if provider.base_url != job.inputs["provider"]["base_url"]:
                    raise UpstreamError("服务商地址已改变，请提交新的任务")
                key = unseal(self.settings.secret_dir, provider.key_encrypted) if provider.protocol != "mock" else None
                images = []
                for asset_id in job.inputs.get("asset_ids", []):
                    asset = db.get(Asset, asset_id)
                    if asset is None or asset.project_id != job.project_id:
                        raise UpstreamError("任务源图片缺失或不属于此项目")
                    try:
                        data = asset_path(self.settings.data_dir, asset_id).read_bytes()
                    except OSError as error:
                        raise UpstreamError("任务源图片缺失或无法读取，请检查项目存储") from error
                    images.append(ImageInput(asset.mime, data))
                db.expunge_all()
            result = asyncio.run(self.perform(job, provider, key, images))
            self.save_result(identifier, generation, result)
        except UpstreamError as error:
            self.mark_failed(identifier, generation, str(error))
        except (ValidationError, KeyError, IndexError, TypeError, AttributeError, ValueError):
            self.mark_failed(identifier, generation, "服务商的响应不符合任务要求，请查看调用记录。")
        except HTTPException as error:
            self.mark_failed(identifier, generation, str(error.detail))
        except Exception as error:
            logger.warning("Task processing failed (%s)", type(error).__name__)
            self.mark_failed(identifier, generation, "处理任务失败，请检查实例存储或运行日志")

    async def perform(self, job, provider, key, images):
        log = Calls(self.sessions, job)
        inputs = job.inputs
        model = inputs["model"]["model_code"] if inputs["model"] else None
        prompt = inputs.get("prompt", "")
        mock = provider.protocol == "mock"
        adapter = None if mock else ADAPTERS[provider.protocol](provider.base_url, key, provider.timeout, log)
        simulated = log.start("mock." + job.kind) if mock else None
        try:
            if job.kind == "probe_connection":
                result = {"message": "Mock 连接成功", "models": ["forma-mock"]} if mock else await adapter.connect()
            elif job.kind == "probe_model":
                result = await self.probe(adapter, model, inputs)
            elif job.kind in IMAGE_TASKS:
                result = mock_images(images, inputs["output"], prompt) if mock else await adapter.images(
                    model, prompt, images, inputs["output"]
                )
                if len(result) != inputs["output"]["count"]:
                    raise UpstreamError("返回图片数量与请求不一致，请检查模型生成数量设置")
            else:
                value = self.mock_text(job) if mock else structured(await adapter.text(model, prompt, images))
                schema = {"optimize": Optimized, "materials": MaterialData}.get(job.kind, Observation)
                result = schema.model_validate(value).model_dump()
        except Exception:
            if simulated:
                log.finish(simulated, "failed")
            raise
        if simulated:
            log.finish(simulated, "succeeded")
        return result

    @staticmethod
    async def probe(adapter, model, inputs):
        capability = inputs["capability"]
        if not adapter:
            return {"message": "Mock 能力测试通过", "capability": capability}
        buffer = io.BytesIO()
        Image.new("RGB", (320, 320), "#79a687").save(buffer, "PNG")
        image = ImageInput("image/png", buffer.getvalue())
        image_protocol = inputs["model"]["capabilities"]
        if capability in {"image_generate", "image_edit"} or capability == "multi_image" and "image_edit" in image_protocol:
            spec = inputs["sizes"][0]
            samples = [image, image] if capability == "multi_image" else [image] if capability == "image_edit" else []
            results = await adapter.images(model, "Render a simple green industrial enclosure.",
                                           samples,
                                           {"count": 1, "ratio": spec["ratio"], "size": spec["value"]})
            if not results:
                raise UpstreamError("模型没有返回图像")
            checked = validate_image(results[0], OUTPUT_LIMIT)
            return {"message": "收到有效图像", "capability": capability,
                    "width": checked.width, "height": checked.height}
        sample = await adapter.text(model, "Reply briefly. If supplied, describe the color of each input image.",
                                    [image, image] if capability == "multi_image" else [image] if capability == "vision" else [])
        if not isinstance(sample, str) or not sample.strip():
            raise UpstreamError("模型没有返回文本")
        return {"message": "收到有效文本", "capability": capability}

    @staticmethod
    def mock_text(job):
        if job.kind == "materials":
            return MOCK_MATERIALS
        if job.kind == "optimize":
            raw = job.inputs["raw"]
            constraints = job.inputs["constraints"]
            return {
                "optimized": "设计目标\n" + raw + "\n\n保留约束\n" + (constraints or "依据原始需求和产品原图确认。")
                + "\n\n呈现要求\n在指定重构幅度内表达外壳比例、分件与材质，并保留可辨认的功能区域。",
                "conflicts": job.inputs.get("warnings", []),
            }
        return {"summary": "Mock 流程示例。可从可见外壳、操作界面和接缝着手记录观察结果。",
                "uncertainties": ["内部结构、尺寸、重量及可制造性待确认。"]}

    def save_result(self, identifier, generation, result):
        stored = []
        try:
            with self.sessions.begin() as db:
                job = db.get(Job, identifier, with_for_update=True)
                if job.status != "running" or job.generation != generation:
                    return
                if job.kind in IMAGE_TASKS:
                    versions = list(db.scalars(select(DesignVersion).where(
                        DesignVersion.job_id == identifier
                    ).order_by(DesignVersion.output_index)))
                    if len(versions) != len(result):
                        raise UpstreamError("任务版本数量不一致")
                    rendered = []
                    for version, content in zip(versions, result, strict=True):
                        asset = store_image(
                            self.settings.data_dir, job.project_id, "result",
                            f"Forma-V{version.number:03d}", content, preserve=True,
                        )
                        stored.append(asset.id)
                        db.add(asset)
                        db.flush()
                        version.asset_id = asset.id
                        rendered.append(asset_view(asset))
                    result = {"version_ids": [version.id for version in versions], "assets": rendered}
                job.result = result
                job.status, job.error, job.lease_until = "succeeded", None, None
        except Exception:
            for asset_id in stored:
                asset_path(self.settings.data_dir, asset_id).unlink(missing_ok=True)
            raise

    def mark_failed(self, identifier, generation, error):
        try:
            with self.sessions.begin() as db:
                job = db.get(Job, identifier, with_for_update=True)
                if job and job.generation == generation and job.status == "running":
                    job.status, job.error, job.lease_until = "failed", error[:400], None
                    db.execute(update(CallLog).where(
                        CallLog.job_id == identifier, CallLog.generation == generation, CallLog.status == "running"
                    ).values(status="failed"))
        except Exception:
            logger.warning("Task failure could not be saved; the lease will expire")
