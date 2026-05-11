"""pytest 共通設定: d-manager/ をインポートルートに加える。"""

from __future__ import annotations

import sys
from pathlib import Path

# tests/ の親（= products/d-manager/）を sys.path に追加し、`import config` 等を可能にする
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
