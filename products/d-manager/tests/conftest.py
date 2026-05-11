"""pytest 共通設定: d-manager/ をインポートルートに加え、config が import できる環境変数を補う。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_D_MANAGER = Path(__file__).resolve().parent.parent  # products/d-manager/
_WORKSPACE = _D_MANAGER.parent.parent  # リポジトリルート

# config.py は import 時に DISCORD_BOT_TOKEN 必須＆.company 配下に mkdir する。
# テスト環境（.env を読まない）でも import が通るよう、未設定なら無害なダミー/実パスを与える。
os.environ.setdefault("DISCORD_BOT_TOKEN", "test-dummy-token")
os.environ.setdefault("COMPANY_DIR", str(_WORKSPACE / ".company"))
# 学習ループDBの import 時の既定値もテスト用に逃がす（各テストは tmp_path で個別に上書きする）
os.environ.setdefault(
    "LEARNING_DB_PATH", str(_D_MANAGER / "learning" / "conversations.test.db")
)

# tests/ の親（= products/d-manager/）を sys.path に追加し、`import config` 等を可能にする
sys.path.insert(0, str(_D_MANAGER))
