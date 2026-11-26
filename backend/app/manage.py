import argparse

from app.config import Settings
from app.db import make_engine, migrate


def main():
    parser = argparse.ArgumentParser(description="Forma AI 管理工具")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate", help="应用数据库迁移")
    args = parser.parse_args()
    settings = Settings.from_env()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    engine = make_engine(settings.database_url)
    try:
        if args.command == "migrate":
            migrate(engine)
            print("数据库迁移完成")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
