from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, BigInteger, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def new_id() -> str:
    return uuid4().hex


class Base(DeclarativeBase):
    pass


class Identity:
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)


class Created:
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Updated(Created):
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)


class User(Identity, Updated, Base):
    __tablename__ = "users"
    username: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="user")
    enabled: Mapped[bool] = mapped_column(default=True)
    must_change_password: Mapped[bool] = mapped_column(default=False)


class LoginSession(Identity, Created, Base):
    __tablename__ = "login_sessions"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    secret_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(index=True)


class LoginFailure(Identity, Created, Base):
    __tablename__ = "login_failures"
    subject: Mapped[str] = mapped_column(String(64), index=True)


class Project(Identity, Updated, Base):
    __tablename__ = "projects"
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    cover_id: Mapped[str | None] = mapped_column(String(32))
    favorite: Mapped[bool] = mapped_column(default=False)
    archived: Mapped[bool] = mapped_column(default=False)
    deleted_at: Mapped[datetime | None]
    next_version: Mapped[int] = mapped_column(default=1)
    demo: Mapped[bool] = mapped_column(default=False)


class Asset(Identity, Created, Base):
    __tablename__ = "assets"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    filename: Mapped[str] = mapped_column(String(200))
    mime: Mapped[str] = mapped_column(String(32))
    width: Mapped[int]
    height: Mapped[int]
    size: Mapped[int]
    sha256: Mapped[str] = mapped_column(String(64))
    deleted_at: Mapped[datetime | None]


class PromptTemplate(Identity, Updated, Base):
    __tablename__ = "prompt_templates"
    slug: Mapped[str] = mapped_column(String(48), unique=True)
    kind: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(80))
    summary: Mapped[str] = mapped_column(String(240))
    body: Mapped[str] = mapped_column(Text)
    sort: Mapped[int] = mapped_column(default=0)
    enabled: Mapped[bool] = mapped_column(default=True)
    revision: Mapped[int] = mapped_column(default=1)


class Provider(Identity, Updated, Base):
    __tablename__ = "providers"
    name: Mapped[str] = mapped_column(String(80), unique=True)
    protocol: Mapped[str] = mapped_column(String(24))
    base_url: Mapped[str] = mapped_column(String(512))
    key_encrypted: Mapped[str | None] = mapped_column(Text)
    timeout: Mapped[int] = mapped_column(default=120)
    concurrency: Mapped[int] = mapped_column(default=1)
    enabled: Mapped[bool] = mapped_column(default=True)


class Model(Identity, Updated, Base):
    __tablename__ = "models"
    __table_args__ = (UniqueConstraint("provider_id", "model_code", name="uq_provider_model"),)
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    model_code: Mapped[str] = mapped_column(String(120))
    capabilities: Mapped[list] = mapped_column(JSON)
    sizes: Mapped[list] = mapped_column(JSON)
    max_count: Mapped[int] = mapped_column(default=1)
    max_inputs: Mapped[int] = mapped_column(default=1)
    pricing: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(default=True)


class ModelBinding(Base):
    __tablename__ = "model_bindings"
    task: Mapped[str] = mapped_column(String(32), primary_key=True)
    model_id: Mapped[str] = mapped_column(ForeignKey("models.id"))


class Job(Identity, Updated, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("user_id", "kind", "request_key", name="uq_job_request"),
        Index("ix_jobs_queue", "status", "created_at"),
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), index=True)
    model_id: Mapped[str | None] = mapped_column(ForeignKey("models.id"))
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    request_key: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="queued")
    inputs: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(String(400))
    generation: Mapped[int] = mapped_column(default=1)
    lease_until: Mapped[datetime | None]


class DesignVersion(Identity, Created, Base):
    __tablename__ = "design_versions"
    __table_args__ = (UniqueConstraint("project_id", "number", name="uq_project_version_number"),)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("design_versions.id"), index=True)
    asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"), unique=True)
    number: Mapped[int]
    output_index: Mapped[int]
    favorite: Mapped[bool] = mapped_column(default=False)


class CallLog(Identity, Created, Base):
    __tablename__ = "call_logs"
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    generation: Mapped[int]
    operation: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(24))
    request_id: Mapped[str | None] = mapped_column(String(160))
    http_status: Mapped[int | None]
    elapsed_ms: Mapped[int | None]
    usage: Mapped[dict | None] = mapped_column(JSON)


class MaterialPrice(Identity, Updated, Base):
    __tablename__ = "material_prices"
    __table_args__ = (
        UniqueConstraint("name", "grade", "spec", "process", "supplier", name="uq_material_price"),
    )
    name: Mapped[str] = mapped_column(String(100))
    grade: Mapped[str] = mapped_column(String(80))
    spec: Mapped[str] = mapped_column(String(120))
    density: Mapped[str | None] = mapped_column(String(40))
    unit_price: Mapped[str] = mapped_column(String(40))
    unit: Mapped[str] = mapped_column(String(8))
    loss_rate: Mapped[str] = mapped_column(String(40))
    process: Mapped[str] = mapped_column(String(120))
    process_price: Mapped[str | None] = mapped_column(String(40))
    supplier: Mapped[str] = mapped_column(String(120))
    source: Mapped[str] = mapped_column(String(160))
    price_date: Mapped[str] = mapped_column(String(10))
    tax_included: Mapped[bool]


class MaterialPlan(Identity, Updated, Base):
    __tablename__ = "material_plans"
    version_id: Mapped[str] = mapped_column(ForeignKey("design_versions.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id"))
    name: Mapped[str] = mapped_column(String(120))
    data: Mapped[dict] = mapped_column(JSON)


class CostPlan(Identity, Updated, Base):
    __tablename__ = "cost_plans"
    version_id: Mapped[str] = mapped_column(ForeignKey("design_versions.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    material_plan_id: Mapped[str | None] = mapped_column(ForeignKey("material_plans.id"))
    name: Mapped[str] = mapped_column(String(120))
    data: Mapped[dict] = mapped_column(JSON)


class AuditEvent(Identity, Created, Base):
    __tablename__ = "audit_events"
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    context: Mapped[dict] = mapped_column(JSON, default=dict)


class Backup(Identity, Created, Base):
    __tablename__ = "backups"
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(16), default="queued")
    size: Mapped[int | None] = mapped_column(BigInteger)
    error: Mapped[str | None] = mapped_column(String(240))
