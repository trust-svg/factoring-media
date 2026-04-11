import os
import pytest
import tempfile

@pytest.fixture
def tmp_db(monkeypatch, tmp_path):
    """テスト用の一時SQLiteDBパスを設定するフィクスチャ"""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("DB_PATH", db_path)
    # db モジュールを再インポートして DB_PATH を反映させる
    import importlib
    import sys
    if "db" in sys.modules:
        importlib.reload(sys.modules["db"])
    return db_path
