import hashlib
import json
import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import DateTime, delete, select, text

from app.models import Asset, Base, CallLog, DesignVersion, Job, Setting, new_id, utcnow
from app.storage import OUTPUT_LIMIT, asset_path

FORMAT = "forma-instance-v1"
EXCLUDED = {"login_sessions", "login_failures", "backups"}
TABLES = [table for table in Base.metadata.sorted_tables if table.name not in EXCLUDED]
MANIFEST_LIMIT = 256 * 1024 * 1024


class BackupError(Exception):
    pass


@contextmanager
def snapshot(engine):
    with engine.connect() as connection:
        if connection.dialect.name == "postgresql":
            connection = connection.execution_options(isolation_level="REPEATABLE READ")
        else:
            connection.exec_driver_sql("BEGIN")
        yield connection


def current_revision(connection):
    return connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()


def zip_name(asset):
    identifier = asset["id"]
    if len(identifier) != 32 or any(char not in "0123456789abcdef" for char in identifier):
        raise BackupError("快照含有无效的图片标识")
    return f"images/{identifier}"


def verify_copy(source, output, record):
    expected = record["size"]
    if not isinstance(expected, int) or not 0 < expected <= OUTPUT_LIMIT:
        raise BackupError("快照中的图片大小无效")
    digest = hashlib.sha256()
    actual = 0
    while chunk := source.read(1024 * 1024):
        actual += len(chunk)
        if actual > expected:
            raise BackupError("图片实际大小与快照不一致")
        digest.update(chunk)
        output.write(chunk)
    if actual != expected or digest.hexdigest() != record["sha256"]:
        raise BackupError("图片校验失败")


def serialize(value):
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Unsupported snapshot value {type(value).__name__}")


def create_snapshot(engine, data_dir: Path, destination: Path):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise BackupError("目标备份文件已存在")
    partial = destination.with_name(f".{destination.name}.{new_id()}.partial")
    try:
        with snapshot(engine) as connection, ZipFile(partial, "x") as archive:
            tables = {table.name: [dict(row) for row in connection.execute(select(table)).mappings()]
                      for table in TABLES}
            manifest = {
                "format": FORMAT, "created_at": utcnow().isoformat() + "Z",
                "revision": current_revision(connection), "tables": tables,
            }
            encoded = json.dumps(manifest, ensure_ascii=False, default=serialize).encode()
            if len(encoded) > MANIFEST_LIMIT:
                raise BackupError("数据库快照清单超过 256 MB")
            archive.writestr("manifest.json", encoded)
            for record in tables[Asset.__tablename__]:
                with asset_path(data_dir, record["id"]).open("rb") as source, archive.open(
                    zip_name(record), "w"
                ) as output:
                    verify_copy(source, output, record)
        if destination.exists():
            raise BackupError("目标备份文件已存在")
        os.replace(partial, destination)
    except OSError as error:
        raise BackupError("无法完成备份，请检查存储空间、文件访问权限或缺失图片") from error
    finally:
        partial.unlink(missing_ok=True)
    return destination.stat().st_size


def validate_bundle(archive: ZipFile, connection):
    files = archive.infolist()
    names = {item.filename for item in files}
    if len(names) != len(files) or "manifest.json" not in names or len(files) > 500_001:
        raise BackupError("备份包含重复、缺失或过多文件")
    if archive.getinfo("manifest.json").file_size > MANIFEST_LIMIT:
        raise BackupError("数据库快照清单超过 256 MB")
    manifest = json.loads(archive.read("manifest.json"))
    if manifest["format"] != FORMAT or manifest["revision"] != current_revision(connection):
        raise BackupError("备份格式或数据库迁移版本不匹配")
    tables = manifest["tables"]
    if set(tables) != {table.name for table in TABLES}:
        raise BackupError("备份实体不完整")
    for table in TABLES:
        columns = set(table.columns.keys())
        if not isinstance(tables[table.name], list) or any(set(row) != columns for row in tables[table.name]):
            raise BackupError("备份实体字段不匹配")
    assets = tables[Asset.__tablename__]
    expected = {zip_name(record) for record in assets} | {"manifest.json"}
    if len(expected) != len(assets) + 1 or expected != names:
        raise BackupError("图片文件与备份清单不一致")
    if any(archive.getinfo(zip_name(row)).file_size != row["size"] for row in assets):
        raise BackupError("图片大小与备份清单不一致")
    return tables


def install_recovery_key(secret_dir, file, tables):
    # The recovery key remains a separate file from the database and images.
    encrypted = [row["key_encrypted"] for row in tables["providers"] if row["key_encrypted"]]
    key = file.read_bytes().strip()
    try:
        cipher = Fernet(key)
        for token in encrypted:
            cipher.decrypt(token.encode())
    except (InvalidToken, ValueError) as error:
        raise BackupError("密钥文件与备份中的服务商凭据不匹配") from error
    path = secret_dir / "provider.key"
    secret_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise BackupError("恢复目标已有密钥，请使用空的密钥卷或省略密钥文件") from error
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(key)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path


def restore_snapshot(engine, settings, bundle: Path, key_file: Path | None = None):
    written = []
    installed_key = None
    try:
        with ZipFile(bundle) as archive, engine.begin() as connection:
            bootstrap = Setting.__table__
            connection.execute(select(bootstrap).where(bootstrap.c.key == "bootstrap").with_for_update()).first()
            for table in TABLES:
                query = select(table).limit(1)
                if table.name == "settings":
                    query = query.where(table.c.key != "bootstrap")
                if connection.execute(query).first():
                    raise BackupError("恢复目标必须为只执行过迁移的空实例")
            tables = validate_bundle(archive, connection)
            assets = tables[Asset.__tablename__]
            for record in assets:
                path = asset_path(settings.data_dir, record["id"])
                path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(zip_name(record)) as source, path.open("xb") as output:
                    written.append(path)
                    verify_copy(source, output, record)
            if key_file:
                installed_key = install_recovery_key(settings.secret_dir, key_file, tables)
            connection.execute(delete(bootstrap))
            for table in TABLES:
                rows = tables[table.name]
                if table.name == DesignVersion.__tablename__:
                    rows.sort(key=lambda row: (row["project_id"], row["number"]))
                for row in rows:
                    for column in table.columns:
                        if isinstance(column.type, DateTime) and row[column.name] is not None:
                            row[column.name] = datetime.fromisoformat(row[column.name])
                    if table.name == Job.__tablename__ and row["status"] in {"queued", "running"}:
                        row.update(status="failed", lease_until=None, updated_at=utcnow(),
                                   error="任务来自恢复的快照。请确认源实例执行情况后再重试。")
                    if table.name == CallLog.__tablename__ and row["status"] == "running":
                        row["status"] = "interrupted"
                if rows:
                    connection.execute(table.insert(), rows)
    except Exception as error:
        for path in written:
            path.unlink(missing_ok=True)
        if installed_key:
            installed_key.unlink(missing_ok=True)
        if isinstance(error, BackupError):
            raise
        if isinstance(error, (BadZipFile, OSError, KeyError, TypeError, ValueError)):
            raise BackupError("备份不可读取、数据格式无效或目标文件已存在") from error
        raise
