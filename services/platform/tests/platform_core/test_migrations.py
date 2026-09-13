from pathlib import Path

from alembic import command
from alembic.config import Config


def test_offline_upgrade_bootstraps_version_table_schema_first(capsys) -> None:
    platform_root = Path(__file__).resolve().parents[2]
    config = Config(platform_root / "alembic.ini")

    command.upgrade(config, "head", sql=True)

    migration_sql = capsys.readouterr().out
    create_schema = migration_sql.index("CREATE SCHEMA IF NOT EXISTS identity")
    create_version_table = migration_sql.index("CREATE TABLE identity.alembic_version")

    assert create_schema < create_version_table
