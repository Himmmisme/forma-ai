import argparse
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from app.backups import BackupError, create_snapshot, restore_snapshot
from app.config import Settings
from app.db import make_engine, migrate


def main():
    parser = argparse.ArgumentParser(description="Forma AI 管理工具")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate", help="应用数据库迁移")
    backup = commands.add_parser("backup", help="创建数据库及图片的完整快照")
    backup.add_argument("file", type=Path)
    restore = commands.add_parser("restore", help="将快照恢复到只执行过迁移的空实例")
    restore.add_argument("file", type=Path)
    restore.add_argument("--key-file", type=Path, help="单独保存的加密密钥文件")
    args = parser.parse_args()
    settings = Settings.from_env()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    engine = make_engine(settings.database_url)
    try:
        if args.command == "migrate":
            migrate(engine)
            print("数据库迁移完成")
        elif args.command == "backup":
            size = create_snapshot(engine, settings.data_dir, args.file)
            print(f"备份完成 · {size} 字节")
        else:
            migrate(engine)
            restore_snapshot(engine, settings, args.file, args.key_file)
            print("恢复完成。启动应用服务后使用原有账号登录。")
    except BackupError as error:
        parser.exit(1, f"{error}\n")
    except SQLAlchemyError:
        parser.exit(1, "数据库操作失败，请检查连接及迁移状态。\n")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
