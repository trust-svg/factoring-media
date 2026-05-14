# Credentials Bitwarden 移行 — Design Spec

**Date**: 2026-05-14
**Author**: Hiro + Claude
**Status**: Draft (要レビュー)
**Origin**: note記事「育てるClaude Codeから"勝手に育つClaude Code"へ」の④汚れにくい体質（Credentials SSoT分）
**Parent spec**: spec #3 (SSoT + flow/stock) の Credentials カテゴリ実装

---

## 1. 目的

散在している `.env` ファイル群を Bitwarden Vault に集約し、Credentials の SSoT を確立する。

### 解決する課題

- ローカルMac + Library/TrustLink + 各プロダクト配下に `.env` が散在
- 同じAPIキーが複数 `.env` で重複している可能性（Anthropic key, Google Ads token等）
- credentials ローテーション時、どの .env を更新すべきか追跡困難
- `.env` バックアップ戦略がない（紛失リスク）
- VPS本番との同期が手動

### 非目標

- Bitwarden Secrets Manager (BWSM)への移行（YAGNI、Password Manager + `bw` CLI で十分）
- ランタイムBitwarden依存化（本番停止リスク回避のため、配布チャネルとしてのみ利用）
- 全 credentials の一括移行（段階的・Phase別）

---

## 2. アーキテクチャ — ハイブリッド方式 (C案)

```
┌─────────────────────────────────────────────────────┐
│ Bitwarden Vault (Cloud, 無料プラン)                 │
│   └─ SSoT として全 credentials を保持               │
└─────────────────────────────────────────────────────┘
                    ▲
                    │ bw login / bw get / bw export
                    │
┌───────────────────┴─────────────────────────────────┐
│ ローカル Mac                                         │
│   ┌──────────────────────────────────────────────┐  │
│   │ ~/.claude/scripts/bw-export-env.sh           │  │
│   │   product 名を渡すと .env を生成             │  │
│   └──────────────────────────────────────────────┘  │
│   ↓                                                  │
│   各プロダクトの .env （gitignore済み・ランタイム）   │
└─────────────────────────────────────────────────────┘
                    │
                    │ rsync / scp (deploy時のみ)
                    ▼
┌─────────────────────────────────────────────────────┐
│ VPS本番 (Contabo東京 46.250.252.99)                 │
│   /opt/apps/<product>/.env （ローカルから配信）      │
│   ※ VPSに bw CLI 不要、Bitwarden障害影響ゼロ        │
└─────────────────────────────────────────────────────┘
```

### 設計の核

- **Bitwarden は配布チャネル**であり、ランタイム依存にしない
- ローカルで `.env` 生成 → ファイル配置（VPSもGitHub Actionsも）
- Bitwarden障害時でも稼働中の本番は無影響
- credentialsローテーション時は「Bitwarden更新 → ローカル再生成 → VPSデプロイ」の3ステップ

---

## 3. Bitwarden Vault 構造

### 3.1 命名規約

各 credentials をBitwardenに「Login」or 「Secure Note」として登録:

```
[product] / [credential_name]
```

例:
- `ebay-agent / EBAY_CLIENT_ID`
- `ebay-agent / EBAY_CLIENT_SECRET`
- `ebay-agent / ANTHROPIC_API_KEY`
- `saimu-media / META_ACCESS_TOKEN`
- `vps / SSH_KEY_TRUSTLINK`
- `shared / ANTHROPIC_API_KEY_PRIMARY`  ← 複数プロダクトで共有

### 3.2 Folder 構造

Bitwarden Folders 機能で整理:
```
Folders/
├── claude-workspace/
│   ├── ebay-agent/
│   ├── saimu-media/
│   ├── faccel/
│   ├── ai-uranai/
│   ├── d-manager/
│   └── threads-auto/
├── infrastructure/
│   ├── vps-trustlink/
│   └── github-actions/
└── shared-keys/
    ├── anthropic/
    ├── google-cloud/
    └── meta-business/
```

### 3.3 重複 credentials の扱い

複数プロダクトで同じキーを使う場合（例: ANTHROPIC_API_KEY）:
- Bitwarden では `shared/<name>` に1つだけ登録
- 各プロダクトの `bw-export-env.sh` で「sharedから取得」と明示
- ローテーション時は1箇所更新で全プロダクト反映

---

## 4. ヘルパースクリプト

### 4.1 `~/.claude/scripts/bw-export-env.sh`

```bash
#!/bin/bash
# Usage: bw-export-env.sh <product-name>
# 例:   bw-export-env.sh ebay-agent > ~/Claude-Workspace/products/ebay-agent/.env

PRODUCT=$1
[ -z "$PRODUCT" ] && echo "Usage: $0 <product-name>" && exit 1

# Bitwarden セッション取得
if [ -z "$BW_SESSION" ]; then
  export BW_SESSION=$(bw unlock --raw)
fi

# 該当productの全itemを抽出してKEY=VALUE形式で出力
bw list items --folderid "$(bw get folder $PRODUCT | jq -r .id)" \
  | jq -r '.[] | "\(.name | split("/")[1])=\(.login.password)"'
```

実行例:
```bash
$ ./bw-export-env.sh ebay-agent > products/ebay-agent/.env
EBAY_CLIENT_ID=xxx
EBAY_CLIENT_SECRET=yyy
ANTHROPIC_API_KEY=zzz
```

### 4.2 `~/.claude/scripts/bw-deploy-env.sh`

```bash
#!/bin/bash
# Usage: bw-deploy-env.sh <product-name> <vps-target>
# ローカルで .env 生成 → VPSにrsync

PRODUCT=$1
VPS_TARGET=$2  # 例: root@46.250.252.99:/opt/apps/<product>/.env

TEMP_ENV=$(mktemp)
~/.claude/scripts/bw-export-env.sh $PRODUCT > $TEMP_ENV

# VPSにrsync (権限600で配置)
rsync -av --chmod=600 $TEMP_ENV $VPS_TARGET

rm $TEMP_ENV
```

### 4.3 `/credentials-rotate` slash command

```markdown
---
description: Credentials のローテーション支援
---

ユーザーが指定したcredentialsをローテーションするフロー:

1. Bitwarden で対象itemを更新（手動・ブラウザ）
2. ローカルで bw-export-env.sh <product> を実行
3. 該当プロダクトのVPSデプロイ実行
4. 旧credentialsの失効確認（API側で）
5. Telegram 通知で完了報告
```

---

## 5. 段階導入フェーズ

### Phase 1: ebay-agent パイロット（1週間）

**目的**: ワークフロー確立、想定外問題の洗い出し

- [ ] Bitwarden に `claude-workspace/ebay-agent/` folder 作成
- [ ] ebay-agent の現状 `.env` を1項目ずつBitwardenに転記
- [ ] `bw-export-env.sh ebay-agent` で .env再生成、現状と diff 確認
- [ ] ローカルで動作確認
- [ ] VPS本番に `bw-deploy-env.sh` でデプロイ、動作確認
- [ ] 1週間運用、問題なければ Phase 2 へ

**ロールバック**: 旧 `.env` を `.env.bak` で保管、即復旧可

### Phase 2: 全ローカルプロダクト .env 移行（1週間）

**目的**: ローカル開発環境を Bitwarden ベースに統一

- [ ] 各プロダクトを順次 Phase 1 と同じ手順で移行
- [ ] 対象: saimu-media, faccel, ai-uranai, d-manager, threads-auto, deal-watcher, b-manager 等
- [ ] 移行完了したプロダクトから旧 .env.bak を削除（1週間観察期間後）

**ロールバック**: .env.bak で個別復旧可

### Phase 3: VPS本番 移行（2週間、最高リスク）

**目的**: 本番環境のcredentialsもBitwarden起点に統一

- [ ] **絶対にプロダクトごとに分散実施**（一気にやらない）
- [ ] 各プロダクトのデプロイ前にバックアップ取得（VPS .env を `.env.bak.YYYYMMDD`）
- [ ] デプロイ後30分は監視（プロセス起動 / Telegram 通知 / 主要機能動作確認）
- [ ] ai-uranai のサイレント未稼働事故を踏まえ「動作確認まで完了して初めて成功」と定義

**ロールバック**: VPSの .env.bak.YYYYMMDD に戻して docker compose restart

**動作確認チェックリスト**（プロダクト別に必須）:
- [ ] コンテナ正常起動（`docker ps` で health check）
- [ ] ログにcredentialsエラーが出ていない
- [ ] 該当プロダクトの主要機能を実行（cron発火 or 手動trigger）
- [ ] Telegram で「正常稼働」通知到達

### Phase 4: GitHub Actions secrets 移行（1週間）

**目的**: CI/CD でも Bitwarden 起点

- [ ] 各リポジトリの GitHub Secrets を `bw-export-env.sh` ベースに置換
- [ ] GitHub Actions 内で `bw` CLI セッション取得（APIキー方式）
- [ ] 注意: GitHubに **Bitwarden API キーは保存必要**（chicken-and-egg、許容）

---

## 6. SSoT Map への反映（spec #3 連動）

spec #3 で定義した「Credentials → 1Password」を以下に修正:

```diff
| Credentials | 1Password Vault | 1Password CLI 経由 |
+ | Credentials | Bitwarden Vault (無料プラン) | bw CLI 経由、配布チャネルとしてのみ利用 |
```

---

## 7. Gotchas / リスク

### リスク1: Bitwarden 障害時の影響

**評価**: ハイブリッド方式（C案）なので、**稼働中の本番は無影響**。ただし以下は影響:
- credentialsローテーション不可（ローカルで `bw` 叩けない）
- 新規プロダクトのセットアップ遅延

**対策**: 緊急時に備えて、Bitwarden の **Emergency Access** 機能を有効化（家族 or 別アカウントに緊急開放権限）。

### リスク2: マスターパスワード紛失

Bitwarden 無料プランは復旧手段が限定的（Emergency Access のみ）。

**対策**:
- 強力なマスターパスワード + 2FA を厳守
- リカバリーコードを物理媒体（紙）で保管
- 4半期に1度、マスターパスワード動作確認（記憶確認）

### リスク3: `bw` CLI セッション切れ

長時間自動化スクリプトを動かす時、セッションがタイムアウトする。

**対策**:
- API キー方式（`bw login --apikey`）でセッション持続
- 自動化スクリプトはAPI キー方式を採用

### リスク4: GitHub Actions の chicken-and-egg

GitHubで Bitwarden を使うには、結局Bitwarden API キーをGitHub Secretsに置く必要がある。

**評価**: 許容範囲。「マスター1個だけGitHubに置く、残りは全部Bitwarden起点」で SSoT は維持される。

### リスク5: VPS .env と Bitwarden の整合性ズレ

VPSで誰か（Hiro本人 or デプロイスクリプト）が .env を直接編集すると、Bitwarden と乖離。

**対策**:
- VPS .env を直接編集する運用を禁止（CLAUDE.md規約化）
- 月次棚卸し（spec #1）で「VPS .env と Bitwarden の整合チェック」を追加検査項目に

### リスク6: 移行中のサイレント未稼働

ai-uranai事故（2026-05-09発覚、8日間サイレント未稼働）の再発。

**対策**:
- Phase 3 の動作確認チェックリスト厳守
- 各プロダクトに hello-world 的なヘルスチェックエンドポイントがあるか事前確認
- なければ移行前に追加

---

## 8. 受け入れ基準

### Phase 1 完了基準
- [ ] Bitwarden に ebay-agent folder + 全 credentials 移行済み
- [ ] `bw-export-env.sh ebay-agent` で .env再生成可能
- [ ] ローカル + VPS両方でebay-agentが正常稼働
- [ ] 1週間運用してエラーゼロ

### Phase 全体完了基準
- [ ] 7プロダクト + 共有キー全て Bitwarden に集約
- [ ] 全VPS本番 .env が Bitwarden起点で配信
- [ ] GitHub Actions も Bitwarden ベースに移行
- [ ] `~/Claude-Workspace/CLAUDE.md` の SSoT Map に Credentials が記載
- [ ] 月次棚卸し（spec #1）に「VPS .env整合チェック」項目追加

---

## 9. 依存関係

- 先行: spec #3（SSoT Map で Credentials カテゴリを定義済み）
- 並列: spec #1（月次棚卸しに整合チェック追加）
- 後続: なし

---

## 10. オープン質問

- Bitwarden Emergency Access の受け手は誰にする？
  → 暫定: 後日検討（Phase 1 完了後）
- VPS deploy 自動化はどこまで踏み込む？（cronで毎日 .env 再配信する？）
  → 暫定: しない。ローテーション時だけ手動デプロイ。頻度を上げると事故源。
