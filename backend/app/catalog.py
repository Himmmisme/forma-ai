import re
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import admin, member, superadmin
from app.core import Input, audit, database, fail, json_fields
from app.models import Model, ModelBinding, PromptTemplate, Provider, Setting, User
from app.prompts import DIRECTIONS, LEVELS, template_view
from app.transport import fixed_endpoint, normalize_endpoint, seal

router = APIRouter(prefix="/design", tags=["设计配置"])
management = APIRouter(prefix="/admin", tags=["AI 管理"])
Capability = Literal["text", "vision", "image_generate", "image_edit", "multi_image"]
Task = Literal["optimize", "inspect", "generate", "edit", "materials", "manufacturing", "cost_advice"]
REAL_PROTOCOLS = ("openai", "gemini", "compatible")
TASK_CAP = {"optimize": "text", "inspect": "vision", "generate": "image_generate", "edit": "image_edit",
            "materials": "vision", "manufacturing": "vision", "cost_advice": "vision"}
MOCK_MODEL = "forma-mock"
MODEL_FIELDS = ("id", "provider_id", "name", "model_code", "capabilities", "sizes", "max_count",
                "max_inputs", "pricing", "enabled")


class ProviderInput(Input):
    name: str = Field(min_length=1, max_length=80)
    protocol: Literal["openai", "gemini", "compatible"]
    base_url: str = Field(default="", max_length=512)
    api_key: str | None = Field(default=None, min_length=1, max_length=4096, repr=False)
    timeout: int = Field(default=120, ge=5, le=180)
    concurrency: int = Field(default=1, ge=1, le=8)
    enabled: bool = True


class ImageSize(Input):
    ratio: str = Field(pattern=r"^([1-9][0-9]?):([1-9][0-9]?)$")
    label: str = Field(min_length=1, max_length=48)
    value: str = Field(pattern=r"^(auto|default|[1-9][0-9]{2,3}x[1-9][0-9]{2,3}|[1-9][0-9]?K|[1-9][0-9]{2,3})$")


class ModelInput(Input):
    name: str = Field(min_length=1, max_length=80)
    model_code: str = Field(min_length=1, max_length=120, pattern=r"^[a-zA-Z0-9_.:@/-]+$")
    provider_id: str = Field(min_length=1, max_length=32)
    capabilities: list[Capability] = Field(min_length=1, max_length=5)
    sizes: list[ImageSize] = Field(default_factory=list, max_length=40)
    max_count: int = Field(default=1, ge=1, le=4)
    max_inputs: int = Field(default=1, ge=1, le=16)
    pricing: str = Field(default="", max_length=3000)
    enabled: bool = True

    @model_validator(mode="after")
    def validate_configuration(self):
        if len(self.capabilities) != len(set(self.capabilities)):
            raise ValueError("能力不得重复")
        if set(self.capabilities) & {"image_generate", "image_edit"} and not self.sizes:
            raise ValueError("图片模型至少需要一个输出规格")
        if len({(item.ratio, item.value) for item in self.sizes}) != len(self.sizes):
            raise ValueError("输出规格不得重复")
        if self.max_inputs > 1 and "multi_image" not in self.capabilities:
            raise ValueError("多张图片需要启用多图输入能力")
        return self


class BindingInput(Input):
    model_id: str | None = Field(default=None, max_length=32)


class TemplateInput(Input):
    name: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=240)
    body: str = Field(min_length=1, max_length=3600)
    sort: int = Field(default=0, ge=-10000, le=10000)
    enabled: bool = True


class TemplateCreate(TemplateInput):
    slug: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,47}$")


def seed_catalog(db: Session):
    if db.get(Setting, "catalog-v1"):
        return
    db.get(Setting, "bootstrap", with_for_update=True)
    if db.get(Setting, "catalog-v1"):
        return
    provider = Provider(name="Forma 本地 Mock", protocol="mock", base_url="", timeout=35, concurrency=4)
    db.add(provider)
    db.flush()
    mock_sizes = [
        {"ratio": "1:1", "label": "1024 × 1024", "value": "1024x1024"},
        {"ratio": "3:2", "label": "1536 × 1024", "value": "1536x1024"},
        {"ratio": "2:3", "label": "1024 × 1536", "value": "1024x1536"},
        {"ratio": "16:9", "label": "1536 × 864", "value": "1536x864"},
        {"ratio": "16:9", "label": "1920 × 1080", "value": "1920x1080"},
    ]
    db.add(Model(
        provider_id=provider.id, name="Forma Mock", model_code=MOCK_MODEL,
        capabilities=["text", "vision", "image_generate", "image_edit", "multi_image"], sizes=mock_sizes,
        max_count=4, max_inputs=16, pricing="本地流程验证",
    ))
    for kind, rows in (("direction", DIRECTIONS), ("level", LEVELS)):
        db.add_all(PromptTemplate(slug=slug, kind=kind, name=name, summary=summary, body=body, sort=10 * idx)
                   for idx, (slug, name, summary, body) in enumerate(rows, 1))
    db.add(Setting(key="catalog-v1", value={"seeded": True}))
    db.commit()


def model_view(model: Model, provider: Provider):
    return {**json_fields(model, *MODEL_FIELDS), "provider_name": provider.name, "protocol": provider.protocol,
            "provider_enabled": provider.enabled}


def provider_view(provider: Provider):
    return {
        **json_fields(provider, "id", "name", "protocol", "base_url", "timeout", "concurrency", "enabled"),
        "has_key": provider.key_encrypted is not None,
    }


def can_serve(model: Model, provider: Provider, task: str) -> bool:
    if not model.enabled or not provider.enabled or TASK_CAP[task] not in model.capabilities:
        return False
    if task == "generate" and provider.protocol in {"openai", "compatible"}:
        return "image_edit" in model.capabilities
    return True


def choose_model(db: Session, task: str, model_id: str | None = None):
    binding = db.get(ModelBinding, task)
    if model_id is None:
        model_id = binding.model_id if binding else None
    query = select(Model, Provider).join(Provider)
    query = query.where(Model.id == model_id) if model_id else query.where(Provider.protocol == "mock")
    row = db.execute(query).first()
    if not row or not can_serve(*row, task):
        fail(422, "未找到启用并支持该任务的模型")
    return row[0], row[1]


def get_provider(db: Session, provider_id: str) -> Provider:
    provider = db.get(Provider, provider_id)
    if not provider:
        fail(404, "服务商不存在")
    return provider


def get_model(db: Session, model_id: str):
    row = db.execute(select(Model, Provider).join(Provider).where(Model.id == model_id)).first()
    if not row:
        fail(404, "模型不存在")
    return row[0], row[1]


@router.get("/catalog")
def public_catalog(db: Session = Depends(database), _: User = Depends(member)):
    templates = db.scalars(select(PromptTemplate).where(PromptTemplate.enabled).order_by(
        PromptTemplate.sort, PromptTemplate.id
    )).all()
    rows = db.execute(select(Model, Provider).where(Model.enabled, Provider.enabled).join(Provider)
                      .order_by(Provider.protocol, Model.name)).all()
    defaults = {binding.task: binding.model_id for binding in db.scalars(select(ModelBinding))}
    mock = next((model.id for model, provider in rows if provider.protocol == "mock"), None)
    models = [{**model_view(model, provider), "tasks": [task for task in TASK_CAP if can_serve(model, provider, task)]}
              for model, provider in rows]
    return {"templates": [template_view(row) for row in templates], "models": models,
            "defaults": {task: defaults.get(task, mock) for task in TASK_CAP}}


@management.get("/catalog")
def admin_catalog(db: Session = Depends(database), _: User = Depends(superadmin)):
    return {
        "providers": [provider_view(row) for row in db.scalars(select(Provider).order_by(Provider.name))],
        "models": [model_view(model, provider) for model, provider in db.execute(select(Model, Provider).join(Provider)
                                                                               .order_by(Model.name))],
        "bindings": {row.task: row.model_id for row in db.scalars(select(ModelBinding))},
    }


def save_provider(body: ProviderInput, request: Request, db: Session, actor: User, provider: Provider | None = None):
    if provider and provider.protocol != body.protocol:
        fail(422, "请新建服务商以更换协议类型")
    endpoint = fixed_endpoint(body.protocol) or normalize_endpoint(body.base_url)
    if body.base_url and body.protocol != "compatible" and body.base_url.rstrip("/") != endpoint:
        fail(422, "官方协议使用固定的 HTTPS 接口地址")
    provider = provider or Provider()
    if provider.base_url and provider.base_url != endpoint and not body.api_key:
        fail(422, "更换 Base URL 后请重新输入该站点的 API Key")
    for key, value in body.model_dump(exclude={"api_key", "base_url"}).items():
        setattr(provider, key, value)
    provider.base_url = endpoint
    if body.api_key:
        provider.key_encrypted = seal(request.app.state.settings.secret_dir, body.api_key)
    if body.enabled and not provider.key_encrypted:
        fail(422, "启用服务商需要 API Key")
    db.add(provider)
    db.flush()
    audit(db, actor, "provider.saved", provider.id, protocol=provider.protocol)
    db.commit()
    return provider_view(provider)


@management.post("/providers", status_code=201)
def create_provider(body: ProviderInput, request: Request, db: Session = Depends(database), actor: User = Depends(superadmin)):
    return save_provider(body, request, db, actor)


@management.put("/providers/{provider_id}")
def edit_provider(provider_id: str, body: ProviderInput, request: Request,
                  db: Session = Depends(database), actor: User = Depends(superadmin)):
    return save_provider(body, request, db, actor, get_provider(db, provider_id))


def save_model(body: ModelInput, db: Session, actor: User, model: Model | None = None):
    provider = get_provider(db, body.provider_id)
    if provider.protocol == "mock" or (model and model.provider_id != provider.id):
        fail(422, "内置模型固定。更换服务商请新建模型。")
    if provider.protocol == "gemini" and any(char in body.model_code for char in "/:@"):
        fail(422, "Gemini 模型 ID 请填写 models/ 之后的名称")
    if provider.protocol in {"openai", "compatible"} and any(
        item.value != "auto" and not re.fullmatch(r"\d+x\d+", item.value) for item in body.sizes
    ):
        fail(422, "OpenAI 图片规格请填写宽x高或 auto")
    if provider.protocol == "gemini" and any(item.value == "auto" or "x" in item.value for item in body.sizes):
        fail(422, "Gemini 图片规格请填模型支持的 imageSize 值，default 表示省略该参数")
    model = model or Model()
    for key, value in body.model_dump().items():
        setattr(model, key, value)
    db.add(model)
    db.flush()
    audit(db, actor, "model.saved", model.id)
    db.commit()
    return model_view(model, provider)


@management.post("/models", status_code=201)
def create_model(body: ModelInput, db: Session = Depends(database), actor: User = Depends(superadmin)):
    return save_model(body, db, actor)


@management.put("/models/{model_id}")
def edit_model(model_id: str, body: ModelInput, db: Session = Depends(database), actor: User = Depends(superadmin)):
    return save_model(body, db, actor, get_model(db, model_id)[0])


@management.put("/bindings/{task}")
def set_binding(task: Task, body: BindingInput, db: Session = Depends(database), actor: User = Depends(superadmin)):
    existing = db.get(ModelBinding, task, with_for_update=True)
    if body.model_id:
        model, provider = get_model(db, body.model_id)
        if not can_serve(model, provider, task):
            fail(422, "此模型未启用或不支持该任务")
        db.merge(ModelBinding(task=task, model_id=model.id))
    elif existing:
        db.delete(existing)
    audit(db, actor, "binding.saved", body.model_id, task=task)
    db.commit()
    return {"task": task, "model_id": body.model_id}


@management.get("/templates")
def templates(db: Session = Depends(database), _: User = Depends(admin)):
    return [template_view(row) for row in db.scalars(select(PromptTemplate).order_by(
        PromptTemplate.kind, PromptTemplate.sort, PromptTemplate.slug
    ))]


@management.post("/templates", status_code=201)
def create_template(body: TemplateCreate, db: Session = Depends(database), actor: User = Depends(admin)):
    template = PromptTemplate(kind="direction", **body.model_dump())
    db.add(template)
    db.flush()
    audit(db, actor, "template.created", template.id)
    db.commit()
    return template_view(template)


@management.put("/templates/{template_id}")
def edit_template(template_id: str, body: TemplateInput, db: Session = Depends(database), actor: User = Depends(admin)):
    template = db.get(PromptTemplate, template_id, with_for_update=True)
    if not template:
        fail(404, "模板不存在")
    if template.kind == "level" and not body.enabled:
        fail(422, "L1–L5 档位需保持启用")
    template.revision += 1
    for key, value in body.model_dump().items():
        setattr(template, key, value)
    audit(db, actor, "template.saved", template.id, revision=template.revision)
    db.commit()
    return template_view(template)
