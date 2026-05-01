"""Phase 2a マイグレーション 0002 のテスト。"""

from alembic.config import Config
from alembic import command
import sqlalchemy as sa


def _make_alembic_config(db_path: str) -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _bootstrap_pre_alembic_jobs(db_path: str) -> None:
    """0001 が前提とする pre-Alembic 期の jobs テーブルを作る。"""
    engine = sa.create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        conn.execute(
            sa.text("""
            CREATE TABLE jobs (
                id INTEGER PRIMARY KEY,
                pattern VARCHAR(4) NOT NULL,
                prompt VARCHAR(2000) NOT NULL,
                status VARCHAR(20) NOT NULL,
                image_path VARCHAR(500),
                video_path VARCHAR(500),
                image_cost_usd FLOAT NOT NULL DEFAULT 0.02,
                video_cost_usd FLOAT NOT NULL DEFAULT 0.0,
                atlas_request_id VARCHAR(200),
                auto_score FLOAT,
                error_message VARCHAR(1000),
                retry_count INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
        """)
        )
        conn.commit()


def test_upgrade_adds_quality_columns_with_low_default(tmp_path):
    db = tmp_path / "test.db"
    _bootstrap_pre_alembic_jobs(str(db))
    cfg = _make_alembic_config(str(db))
    command.upgrade(cfg, "head")

    engine = sa.create_engine(f"sqlite:///{db}")
    with engine.connect() as conn:
        cols_jobs = {r[1] for r in conn.execute(sa.text("PRAGMA table_info(jobs)"))}
        assert "quality" in cols_jobs
        cols_templates = {
            r[1] for r in conn.execute(sa.text("PRAGMA table_info(templates)"))
        }
        assert "default_quality" in cols_templates


def test_existing_rows_backfilled_to_low(tmp_path):
    db = tmp_path / "test.db"
    _bootstrap_pre_alembic_jobs(str(db))
    cfg = _make_alembic_config(str(db))
    command.upgrade(cfg, "7316290cb6fe")

    engine = sa.create_engine(f"sqlite:///{db}")
    with engine.connect() as conn:
        conn.execute(
            sa.text("""
            INSERT INTO jobs (status, prompt, provider, aspect_ratio,
                              duration_seconds, image_source, image_cost_usd,
                              video_cost_usd, retry_count, created_at, updated_at)
            VALUES ('DONE', 'p', 'seedance', '9:16', 10, 'generated',
                    0.02, 0.0, 0, '2026-05-01 00:00:00', '2026-05-01 00:00:00')
        """)
        )
        conn.execute(
            sa.text("""
            INSERT INTO templates (name, category, image_prompt, video_prompt,
                                   default_provider, default_aspect, default_duration,
                                   is_archived, created_at, updated_at)
            VALUES ('T', 'custom', 'i', 'v', 'seedance', '9:16', 10, 0,
                    '2026-05-01 00:00:00', '2026-05-01 00:00:00')
        """)
        )
        conn.commit()

    command.upgrade(cfg, "head")

    with engine.connect() as conn:
        row = conn.execute(sa.text("SELECT quality FROM jobs")).fetchone()
        assert row[0] == "low"
        row = conn.execute(
            sa.text("SELECT default_quality FROM templates WHERE name='T'")
        ).fetchone()
        assert row[0] == "low"


def test_downgrade_removes_quality_columns(tmp_path):
    db = tmp_path / "test.db"
    _bootstrap_pre_alembic_jobs(str(db))
    cfg = _make_alembic_config(str(db))
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "-1")

    engine = sa.create_engine(f"sqlite:///{db}")
    with engine.connect() as conn:
        cols_jobs = {r[1] for r in conn.execute(sa.text("PRAGMA table_info(jobs)"))}
        assert "quality" not in cols_jobs
        cols_templates = {
            r[1] for r in conn.execute(sa.text("PRAGMA table_info(templates)"))
        }
        assert "default_quality" not in cols_templates
