from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

def test_initial_migration(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db = tmp_path / "migration.db"
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    command.upgrade(cfg, "head")
    engine = create_engine(f"sqlite:///{db}")
    assert {"sources", "raw_events", "alembic_version"} <= set(inspect(engine).get_table_names())
    command.downgrade(cfg, "base")
    assert "sources" not in inspect(engine).get_table_names()
