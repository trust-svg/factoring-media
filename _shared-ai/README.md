# _shared-ai/ — Claude Code & Codex 共通スキル領域

Claude Code と Codex から同一実体を参照する「共通セカンドブレイン」の中核。
スキルの**正本（single source of truth）は `_shared-ai/skills/`** で、ここだけが git 追跡される。
各ツールはこの実体への symlink 経由でネイティブにスキルを起動する。

## ディレクトリ構成

```
_shared-ai/
├── README.md                  ← このファイル
├── setup-symlinks.sh          ← symlink を冪等に再生成（クローン先・復旧時に実行）
├── skills/                    ← 共通スキルの正本（git追跡）
│   ├── skill-quality-checker/
│   ├── mcp-audit/
│   ├── factcheck-ai-cross/
│   └── codex-handoff/
└── _legacy-codex-bridges/     ← 旧 .agents/skills/ の退避（プラグイン由来の手動ブリッジ）
```

## スキル配置の判断基準（L1 / L2 / L3）

| レイヤ | 置き場所 | 使うツール | 例 |
|--------|----------|-----------|-----|
| **L1** | `~/.claude/skills/` または `~/.codex/skills/` 直 | 片方のツール専用 | ツール固有の操作スキル |
| **L2** | **`_shared-ai/skills/`（ここ）** | Claude・Codex 両方 | skill-quality-checker など本領域の4本 |
| **L3** | 各プロジェクトの `.claude/skills/` | 1プロジェクト限定 | note-auto 等 |

新スキルを作るときは「何ツール・何プロジェクトで使うか」で置き場所を決める。両ツール共通なら L2＝ここ。

## symlink 経路（3経路・確度別）

正本 `_shared-ai/skills/<name>` を次の3経路から参照する。`setup-symlinks.sh` が全て張る。

- **Claude Code（主・確実）**: `~/.claude/skills/<name>` → `/起動`できる（note-auto で実証済）
- **Codex（主・確実）**: `~/.codex/skills/<name>` → 公式の1階層 `<skill-name>/` 仕様に準拠
- **Codex（補助・要実機確認）**: `.agents/skills/<name>` → リポジトリスコープが効くかは未検証。効けばボーナス

`~/.codex/skills/` への書き込みは sandbox で禁止されているため、`~/.claude/settings.json` の
`sandbox.filesystem.allowWrite` に `/Users/Mac_air/.codex/skills` を**ピンポイントで**追加済み
（`~/.codex` 全体は auth.json / config.toml を含むため絶対に追加しない）。

## setup-symlinks.sh の使い方

```bash
bash _shared-ai/setup-symlinks.sh
```

- 冪等（`ln -sfn`）。何度実行しても安全。スキルを追加したら配列に名前を足して再実行
- 新マシン・クローン直後・symlink が壊れたときの復旧に使う
- sandbox 設定変更（`/Users/Mac_air/.codex/skills` の許可）を反映するには Claude Code の**再起動が必要**

## 棚卸し3サイクル

| 対象 | 頻度 | 手段 |
|------|------|------|
| MCP サーバ | 月1 or `/context` で MCP が 5% 超 | `mcp-audit` スキル |
| 未使用スキル | 隔週（手動） | 直近で発火していないスキルを点検 |
| ephemeral / cache | 四半期（手動） | 一時ファイル・古いキャッシュの掃除 |

## `_legacy-codex-bridges/` の経緯

`.agents/skills/` に置かれていた7スキル（ai-secretary / build-site / cro-methodology / ebay /
funnel-analysis / i18n / sns-research）は、Claude Code プラグイン由来のスキルを Codex から読ませる
ための**手動コピー（ブリッジ）**だった。git 未追跡・更新停止で死蔵気味だったため、削除せずここへ退避して
git 記録した。Codex のリポジトリスコープ自動スキャンが一次ドキュメントで確認できないため、これらが実際に
機能していたかは不明。保全目的の退避であり、必要なら復元できる。
