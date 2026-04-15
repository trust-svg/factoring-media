# eBay AI Agent 統合開発企画

## Context

@junichi_ushiku（うっしー@ebay輸出×AI）の活動と業界トレンドを調査した結果、eBay輸出×AI自動化の最前線では「個別ツール」ではなく「パイプライン（需要検知→仕入れ→出品→価格最適化→分析）」が競争力の源泉になっている。現在のプロダクト群（4ツール）は個々に優秀だが、完全に分断されている。これを統合する「eBay AI Agent Hub」を構築し、業界のベストプラクティスを自社に取り込む。

### 調査で判明した業界トレンド
- **写真→出品**: 商品写真をAIに読ませて3分で出品完了
- **テラピーク×AI**: 売れ筋データをGPT/Claudeで分析、仕入れ候補を一括取得
- **n8n/MCPワークフロー**: AI AgentがeBay APIを直接操作（36オペレーション対応）
- **動的価格調整**: 競合価格+為替レートを考慮した自動リプライシング
- **バイヤー対応AI**: 購入者メッセージへの自動返信ドラフト生成

### 現在のプロダクト群 vs ギャップ

| 既存ツール | できること |
|---|---|
| ebay-inventory-tool | 在庫切れ検知 + 5マーケットプレイス仕入れ検索 |
| ebay-listing-generator | AI出品タイトル/説明文生成（Chrome拡張） |
| ebay-listing-optimizer | SEO分析+最適化+競合分析（FastAPI+Chrome拡張） |
| size-lookup | 梱包サイズ推定+HTSコード検索（Chrome拡張） |

| 不足している機能 | 影響度 |
|---|---|
| ツール間の連携パイプライン | CRITICAL |
| 価格インテリジェンス（競合モニタリング+自動調整） | HIGH |
| 需要検知→仕入れ→出品の一気通貫フロー | HIGH |
| 売上分析ダッシュボード（利益追跡） | HIGH |
| バイヤーメッセージAI対応 | MEDIUM |
| MCP Server化（Claude Desktop連携） | MEDIUM |

---

## 開発計画

### Phase 1: 統合基盤 `products/ebay-agent/` の構築（2-3週間）

新規ディレクトリ `products/ebay-agent/` を作成し、既存4ツールを統合するFastAPIサーバーを構築する。

#### 1A. 共通eBayクライアント統合
- `ebay_core/client.py` — ebay-inventory-tool と ebay-listing-optimizer のOAuth/API処理を統合
- 対象ファイル:
  - `products/ebay-inventory-tool/ebay_client.py`（OAuth + Sell Inventory API + Trading API）
  - `products/ebay-listing-optimizer/ebay/auth.py` + `ebay/listings.py`

#### 1B. ツールレジストリ
- `tools/registry.py` — 各ツールをClaude tool_useパターンで呼び出し可能にする
- 登録ツール: `check_inventory`, `search_sources`, `generate_listing`, `analyze_seo`, `optimize_listing`, `estimate_packaging`, `get_exchange_rate`, `apply_changes`

#### 1C. 既存コードのラッパー関数
- 既存ツールを**書き換えず**にインポート+ラップ
- listing-generatorのシステムプロンプト（JS→Python移植）
- inventory-toolのスクレイパー群を関数として呼び出し可能に

#### 1D. 統合データベース
- SQLAlchemy + SQLite（本番はPostgreSQL/Railway）
- 追加テーブル: `SourceCandidate`（仕入れ候補）, `PriceHistory`（価格履歴）, `SalesRecord`（売上記録）
- 既存パターン: `products/ebay-listing-optimizer/database/models.py` を拡張

#### 1E. 統合ダッシュボード
- FastAPI + Jinja2テンプレート（optimizer既存パターン流用）
- 全ツールの状態を一画面で確認

---

### Phase 2: 価格インテリジェンスエンジン（2週間）

現在**完全に欠落**している最大のギャップを埋める。

#### 2A. 競合価格モニター
- `pricing/monitor.py` — eBay Browse APIで競合出品の価格を定期取得
- 6時間ごとにスケジュール実行、PriceHistoryテーブルに蓄積
- 既存パターン: `ebay-listing-optimizer/ebay/competitor.py` を拡張

#### 2B. AI価格アドバイザー
- `pricing/advisor.py` — Claude tool_useで価格提案
- 入力: 現在価格 + 競合価格 + 為替レート + 仕入れ原価 + 売れ行き
- 出力: 推奨価格 + 理由 + 利益率予測

#### 2C. 人間承認付き自動価格更新
- ダッシュボードで承認 → eBay APIで価格更新
- 既存パターン: `ebay-listing-optimizer/api/apply.py`

---

### Phase 3: 需要検知→出品パイプライン（3週間）

@junichi_ushiくが重視している「売れるものを見つけて仕入れて出品する」一気通貫フロー。

#### 3A. 需要検知モジュール
- `research/demand.py`
- eBay完了リスト（売れた商品）を分析 → 売れ筋率・平均価格を算出
- 日本のマーケットプレイスと価格照合 → 利益が出る商品をランク付け

#### 3B. AIリサーチエージェント
- `research/agent.py` — Claude tool_useエージェント
- ツール: `search_ebay_sold`, `search_ebay_active`, `search_japanese_source`, `calculate_margin`
- 「ビンテージシンセサイザーで利益が出る商品を見つけて」のような自然言語指示に対応

#### 3C. ワンクリックパイプライン
1. リサーチエージェントが有望商品を特定
2. 日本のマーケットプレイスで仕入れ候補を検索（既存スクレイパー流用）
3. listing-generatorの最適化プロンプトでタイトル+説明文を生成
4. 梱包サイズを推定
5. ダッシュボードで確認 → ワンクリックでeBayに出品

---

### Phase 4: コミュニケーション＆分析（2週間）

#### 4A. バイヤーメッセージAI
- `comms/buyer_messages.py`
- eBay Post-Order APIでバイヤーメッセージ取得
- Claudeで返信ドラフト生成（送信前に人間確認）

#### 4B. 売上分析ダッシュボード
- 売上・利益追跡（日次/週次/月次）
- カテゴリ別パフォーマンス
- 在庫回転率、為替影響分析

#### 4C. 通知強化
- LINE Flex Messageでリッチ通知
- 新規売上、競合価格アラート、有望商品発見を通知

---

### Phase 5: MCP Server化 & CLI（2週間）

#### 5A. MCPサーバー
- `mcp_server.py` — 全機能をMCPプロトコルで公開
- Claude DesktopやClaude Codeから直接eBay操作可能に

#### 5B. CLIインターフェース
```bash
ebay-agent inventory              # 在庫チェック
ebay-agent source "Pioneer CDJ"   # 仕入れ検索
ebay-agent list "Nakamichi Dragon" # 出品作成
ebay-agent price-check --sku XYZ   # 競合価格チェック
ebay-agent research "vintage synths" # 需要分析
```

---

## 技術スタック

| 項目 | 技術 | 理由 |
|---|---|---|
| バックエンド | FastAPI (Python 3.10+) | ebay-listing-optimizerと統一 |
| DB | SQLAlchemy + SQLite → PostgreSQL | 既存パターン流用 |
| AI | Anthropic SDK (Claude) | 既存ツールと統一 |
| スクレイピング | Playwright + BeautifulSoup4 | inventory-toolと統一 |
| スケジューリング | APScheduler | マルチジョブ対応 |
| 通知 | LINE + Gmail | 既存notifier.py流用 |
| デプロイ | Railway | ai-uranaiと統一 |

## 重要ファイル（実装時に参照）

- `products/ebay-inventory-tool/ebay_client.py` — eBay OAuth+APIクライアント
- `products/ebay-listing-generator/lib/ai-api.js` — 出品生成AIプロンプト（240行、Python移植対象）
- `products/ebay-listing-optimizer/optimizer/agent.py` — Claude tool_useエージェントパターン
- `products/ebay-listing-optimizer/database/models.py` — SQLAlchemyモデルパターン
- `products/ebay-inventory-tool/scrapers/base_scraper.py` — スクレイパー基底クラス

## 検証方法

1. **Phase 1**: `ebay-agent` サーバー起動 → 各ツールのAPI呼び出しが成功することを確認
2. **Phase 2**: 競合価格取得 → AI価格提案 → ダッシュボード表示を確認
3. **Phase 3**: カテゴリ指定 → 需要分析 → 仕入れ候補 → 出品ドラフト生成の一連フローを確認
4. **Phase 4**: バイヤーメッセージ取得 → AI返信ドラフト生成を確認
5. **Phase 5**: `claude-code` からMCPツールとしてeBay操作ができることを確認

## 優先順位

| Phase | 影響度 | 工数 | 順序 |
|---|---|---|---|
| 1. 統合基盤 | CRITICAL | 2-3週間 | 最初に着手 |
| 2. 価格エンジン | HIGH | 2週間 | 2番目 |
| 3. 需要パイプライン | HIGH | 3週間 | 3番目 |
| 4. コミュニケーション＆分析 | MEDIUM | 2週間 | 4番目 |
| 5. MCP & CLI | MEDIUM | 2週間 | 5番目 |

**合計: 約10-12週間**
