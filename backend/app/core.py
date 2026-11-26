from collections.abc import Iterator
from datetime import datetime

from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.models import AuditEvent, User


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def database(request: Request) -> Iterator[Session]:
    with request.app.state.sessions() as session:
        yield session


def json_fields(row, *fields):
    result = {}
    for name in fields:
        value = getattr(row, name)
        result[name] = iso(value) if isinstance(value, datetime) else value
    return result


def iso(value: datetime) -> str:
    return value.isoformat(timespec="microseconds") + "Z"


def fail(status: int, message: str):
    raise HTTPException(status, message)


def audit(db: Session, actor: User | None, action: str, entity: str | None = None, **context):
    db.add(AuditEvent(user_id=actor.id if actor else None, action=action, entity_id=entity, context=context))
