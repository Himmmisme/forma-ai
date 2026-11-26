import hashlib
import secrets
from datetime import timedelta
from typing import Annotated, Literal

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import APIRouter, Depends, Request, Response
from pydantic import StringConstraints, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core import Input, audit, database, fail, json_fields
from app.models import LoginFailure, LoginSession, Setting, User, utcnow

router = APIRouter(prefix="/auth", tags=["账号"])
admin_router = APIRouter(prefix="/admin/users", tags=["账号管理"])
COOKIE = "forma_session"
SESSION_AGE = timedelta(hours=24)
RATE_WINDOW = timedelta(minutes=10)
PASSWORDS = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
DUMMY_HASH = PASSWORDS.hash(secrets.token_urlsafe(32))
Username = Annotated[str, StringConstraints(min_length=3, max_length=40, pattern=r"^[a-zA-Z0-9_.-]+$")]
DisplayName = Annotated[str, StringConstraints(min_length=1, max_length=80)]
Password = Annotated[str, StringConstraints(min_length=12, max_length=128, strip_whitespace=False)]


class Credentials(Input):
    username: Username
    password: Annotated[str, StringConstraints(min_length=1, max_length=128, strip_whitespace=False)]

    @field_validator("username")
    @classmethod
    def normalize_username(cls, name: str):
        return name.lower()


class NewUser(Credentials):
    name: DisplayName
    password: Password


class SetupUser(NewUser):
    token: Annotated[str, StringConstraints(min_length=1, max_length=200, strip_whitespace=False)]


class ManagedUser(NewUser):
    role: Literal["user", "admin", "superadmin"] = "user"


class AccountUpdate(Input):
    name: DisplayName | None = None
    role: Literal["user", "admin", "superadmin"] | None = None
    enabled: bool | None = None


class Profile(Input):
    name: DisplayName


class PasswordChange(Input):
    current_password: Annotated[str, StringConstraints(min_length=1, max_length=128, strip_whitespace=False)]
    password: Password


class PasswordReset(Input):
    password: Password


def user_view(user: User):
    return json_fields(user, "id", "username", "name", "role", "enabled", "must_change_password", "created_at")


def digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def compare_password(password_hash: str, password: str) -> bool:
    try:
        return PASSWORDS.verify(password_hash, password)
    except VerificationError:
        return False


def current_user(request: Request, db: Session = Depends(database)) -> User:
    secret = request.cookies.get(COOKIE, "")
    if not 32 <= len(secret) <= 100:
        fail(401, "请先登录")
    user = db.scalar(
        select(User)
        .join(LoginSession)
        .where(LoginSession.secret_hash == digest(secret), LoginSession.expires_at > utcnow(), User.enabled)
    )
    if not user:
        fail(401, "登录已过期，请重新登录")
    return user


def member(user: User = Depends(current_user)) -> User:
    if user.must_change_password:
        fail(403, "请先修改临时密码")
    return user


def admin(user: User = Depends(member)) -> User:
    if user.role not in {"admin", "superadmin"}:
        fail(403, "需要管理员权限")
    return user


def superadmin(user: User = Depends(admin)) -> User:
    if user.role != "superadmin":
        fail(403, "需要超级管理员权限")
    return user


def new_session(db: Session, user: User, request: Request, response: Response):
    secret = secrets.token_urlsafe(32)
    db.add(LoginSession(user_id=user.id, secret_hash=digest(secret), expires_at=utcnow() + SESSION_AGE))
    response.set_cookie(
        COOKIE,
        secret,
        max_age=int(SESSION_AGE.total_seconds()),
        httponly=True,
        secure=request.app.state.settings.cookie_secure,
        samesite="strict",
    )


def revoke_sessions(db: Session, user_id: str):
    db.execute(delete(LoginSession).where(LoginSession.user_id == user_id))


def reset_expired(db: Session):
    db.execute(delete(LoginSession).where(LoginSession.expires_at <= utcnow()))
    db.execute(delete(LoginFailure).where(LoginFailure.created_at < utcnow() - RATE_WINDOW))


def login_limits(db: Session, request: Request, username: str) -> list[str]:
    host = request.client.host if request.client else "unknown"
    subjects = [(digest(f"host:{host}"), 25), (digest(f"login:{host}:{username}"), 8)]
    for subject, limit in subjects:
        count = db.scalar(
            select(func.count()).select_from(LoginFailure)
            .where(LoginFailure.subject == subject, LoginFailure.created_at >= utcnow() - RATE_WINDOW)
        )
        if count >= limit:
            fail(429, "尝试次数过多，请十分钟后重试")
    return [subject for subject, _ in subjects]


@router.get("/setup")
def setup_status(request: Request, db: Session = Depends(database)):
    return {
        "initialized": db.get(Setting, "bootstrap").value["initialized"],
        "available": len(request.app.state.settings.setup_token) >= 24,
    }


@router.post("/setup", status_code=201)
def setup(body: SetupUser, request: Request, response: Response, db: Session = Depends(database)):
    with request.app.state.write_lock:
        state = db.get(Setting, "bootstrap", with_for_update=True)
        if state.value["initialized"]:
            fail(409, "平台已初始化")
        configured = request.app.state.settings.setup_token
        if len(configured) < 24:
            fail(503, "请由部署者配置初始化令牌")
        subjects = login_limits(db, request, "__setup__")
        if not secrets.compare_digest(configured.encode(), body.token.encode()):
            db.add_all(LoginFailure(subject=subject) for subject in subjects)
            reset_expired(db)
            db.commit()
            fail(403, "初始化令牌错误")
        user = User(username=body.username, name=body.name, password_hash=PASSWORDS.hash(body.password),
                    role="superadmin")
        db.add(user)
        db.flush()
        state.value = {"initialized": True}
        new_session(db, user, request, response)
        audit(db, user, "system.initialized", user.id)
        db.commit()
    return user_view(user)


@router.post("/login")
def login(body: Credentials, request: Request, response: Response, db: Session = Depends(database)):
    with request.app.state.write_lock:
        subjects = login_limits(db, request, body.username)
        user = db.scalar(select(User).where(User.username == body.username).with_for_update())
        valid = compare_password(user.password_hash if user else DUMMY_HASH, body.password)
        if not (user and user.enabled and valid):
            db.add_all(LoginFailure(subject=subject) for subject in subjects)
            reset_expired(db)
            db.commit()
            fail(401, "账号或密码错误")
        if PASSWORDS.check_needs_rehash(user.password_hash):
            user.password_hash = PASSWORDS.hash(body.password)
        reset_expired(db)
        new_session(db, user, request, response)
        audit(db, user, "auth.login", user.id)
        db.commit()
    return user_view(user)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(database)):
    secret = request.cookies.get(COOKIE, "")
    if 32 <= len(secret) <= 100:
        db.execute(delete(LoginSession).where(LoginSession.secret_hash == digest(secret)))
        db.commit()
    response.delete_cookie(COOKIE, httponly=True, samesite="strict", secure=request.app.state.settings.cookie_secure)


@router.get("/me")
def me(user: User = Depends(current_user)):
    return user_view(user)


@router.patch("/me")
def update_profile(body: Profile, db: Session = Depends(database), user: User = Depends(member)):
    user.name = body.name
    db.commit()
    return user_view(user)


@router.post("/password")
def change_password(
    body: PasswordChange,
    request: Request,
    response: Response,
    db: Session = Depends(database),
    user: User = Depends(current_user),
):
    with request.app.state.write_lock:
        locked = db.get(User, user.id, with_for_update=True, populate_existing=True)
        if not locked.enabled or not compare_password(locked.password_hash, body.current_password):
            fail(403, "当前密码有误")
        locked.password_hash = PASSWORDS.hash(body.password)
        locked.must_change_password = False
        revoke_sessions(db, locked.id)
        new_session(db, locked, request, response)
        audit(db, locked, "auth.password_changed", locked.id)
        db.commit()
    return user_view(locked)


def manageable_user(db: Session, actor: User, user_id: str) -> User:
    target = db.get(User, user_id, with_for_update=True, populate_existing=True)
    if not target or (actor.role == "admin" and target.role != "user"):
        fail(404, "用户不存在或不可管理")
    if target.id == actor.id:
        fail(409, "请在个人设置中维护自己的账号")
    return target


@admin_router.get("")
def list_users(db: Session = Depends(database), actor: User = Depends(admin), offset: int = 0):
    query = select(User)
    if actor.role == "admin":
        query = query.where(User.role == "user")
    return [user_view(user) for user in db.scalars(query.order_by(User.username).offset(max(0, offset)).limit(200))]


@admin_router.post("", status_code=201)
def create_user(body: ManagedUser, db: Session = Depends(database), actor: User = Depends(admin)):
    if actor.role == "admin" and body.role != "user":
        fail(403, "管理员可创建普通用户")
    if db.scalar(select(User.id).where(User.username == body.username)):
        fail(409, "账号名称已存在")
    target = User(
        username=body.username, name=body.name, role=body.role,
        password_hash=PASSWORDS.hash(body.password), must_change_password=True,
    )
    db.add(target)
    db.flush()
    audit(db, actor, "user.created", target.id, role=target.role)
    db.commit()
    return user_view(target)


@admin_router.patch("/{user_id}")
def edit_user(user_id: str, body: AccountUpdate, db: Session = Depends(database), actor: User = Depends(admin)):
    target = manageable_user(db, actor, user_id)
    if body.role is not None and actor.role == "admin" and body.role != "user":
        fail(403, "需要超级管理员权限")
    if target.role == "superadmin" and (body.enabled is False or body.role not in {None, "superadmin"}):
        # Serialize changes to the last privileged account.
        db.get(Setting, "bootstrap", with_for_update=True)
        count = db.scalar(select(func.count()).select_from(User).where(
            User.enabled, User.role == "superadmin", User.id != target.id
        ))
        if not count:
            fail(409, "系统至少需要一个启用的超级管理员")
    changes = body.model_dump(exclude_none=True)
    if "enabled" in changes or "role" in changes:
        revoke_sessions(db, target.id)
    for field, value in changes.items():
        setattr(target, field, value)
    audit(db, actor, "user.updated", target.id, fields=list(changes))
    db.commit()
    return user_view(target)


@admin_router.post("/{user_id}/password", status_code=204)
def reset_password(user_id: str, body: PasswordReset, db: Session = Depends(database), actor: User = Depends(admin)):
    target = manageable_user(db, actor, user_id)
    target.password_hash = PASSWORDS.hash(body.password)
    target.must_change_password = True
    revoke_sessions(db, target.id)
    audit(db, actor, "user.password_reset", target.id)
    db.commit()
