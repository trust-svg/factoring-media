"""ツールレジストリ — Claude tool_use パターンで全機能を公開

各既存ツールの機能をClaude APIのtool定義として登録し、
AIエージェントが自律的に呼び出せるようにする。
"""
from __future__ import annotations

AGENT_TOOLS: list[dict] = [
    # ── 在庫管理 ──
    {
        "name": "check_inventory",
        "description": "eBayのアクティブ出品を取得し、在庫状況を確認する。在庫切れアイテムのリストを返す。",
        "input_schema": {
            "type": "object",
            "properties": {
                "out_of_stock_only": {
                    "type": "boolean",
                    "description": "trueなら在庫切れアイテムのみ返す",
                    "default": False,
                },
            },
        },
    },
    # ── 仕入れ検索 ──
    {
        "name": "search_sources",
        "description": (
            "登録済み日本マーケットプレイス（ヤフオク・メルカリ・ブックオフ・駿河屋・Yahoo!フリマ）で商品を検索し、"
            "AI画像比較＋型番フィルタ＋スコアリングで最適な仕入れ候補を返す。"
            "【重要】ebay_image_url を必ず指定すること。画像比較なしでは別商品を拾いやすく精度が大幅に低下する。"
            "画像URLが不明な場合は先に check_inventory で出品情報を取得してから呼ぶこと。"
            "汎用Web検索による仕入れは行わない（登録サイトのみ巡回）。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "検索キーワード（日本語）。型番がある商品は型番を含めると精度向上（例: 'Pioneer CDJ-2000NXS2'）",
                },
                "max_price_jpy": {
                    "type": "integer",
                    "description": "価格上限（円）",
                    "default": 50000,
                },
                "junk_ok": {
                    "type": "boolean",
                    "description": "ジャンク品を含むか",
                    "default": False,
                },
                "ebay_image_url": {
                    "type": "string",
                    "description": "【推奨必須】eBay出品画像URL（AI画像比較に使用）。未指定時は画像比較なしで精度低下。",
                },
                "top_n": {
                    "type": "integer",
                    "description": "返す候補数（デフォルト5）",
                    "default": 5,
                },
                "sites": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "巡回サイトを絞る場合に指定（例: ['yahoo_auctions', 'mercari']）。省略時は全有効サイト。",
                    "default": [],
                },
            },
            "required": ["keyword"],
        },
    },
    # ── 出品生成 ──
    {
        "name": "generate_listing",
        "description": "AIを使ってeBay出品のタイトル・説明文・スペックを生成する。3つのタイトルバリエーション付き。",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_name": {
                    "type": "string",
                    "description": "商品名（ブランド名+モデル名）",
                },
                "category": {
                    "type": "string",
                    "description": "商品カテゴリ",
                    "default": "",
                },
                "condition": {
                    "type": "string",
                    "description": "商品の状態",
                    "default": "",
                },
                "competitor_keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "競合のキーワード（SEO参考）",
                    "default": [],
                },
            },
            "required": ["product_name"],
        },
    },
    # ── SEO分析 ──
    {
        "name": "analyze_seo",
        "description": "既存eBay出品のSEOスコアを分析する。タイトル・説明文・スペック・写真の各スコアを返す。",
        "input_schema": {
            "type": "object",
            "properties": {
                "sku": {
                    "type": "string",
                    "description": "分析対象のSKU",
                },
            },
            "required": ["sku"],
        },
    },
    # ── 出品最適化 ──
    {
        "name": "optimize_listing",
        "description": "AIを使って既存eBay出品のタイトル・説明文を最適化する。改善提案と理由を返す。",
        "input_schema": {
            "type": "object",
            "properties": {
                "sku": {
                    "type": "string",
                    "description": "最適化対象のSKU",
                },
            },
            "required": ["sku"],
        },
    },
    # ── eBay検索 ──
    {
        "name": "search_ebay",
        "description": "eBay Browse APIで商品を検索する（競合分析・市場調査用）。",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "検索クエリ（英語）",
                },
                "limit": {
                    "type": "integer",
                    "description": "最大取得件数",
                    "default": 20,
                },
            },
            "required": ["query"],
        },
    },
    # ── 価格分析 ──
    {
        "name": "analyze_pricing",
        "description": "指定SKUの競合価格を分析し、推奨価格と理由を返す。",
        "input_schema": {
            "type": "object",
            "properties": {
                "sku": {
                    "type": "string",
                    "description": "価格分析対象のSKU",
                },
            },
            "required": ["sku"],
        },
    },
    # ── 為替レート ──
    {
        "name": "get_exchange_rate",
        "description": "現在のUSD→JPY為替レートを取得する。",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    # ── 利益計算 ──
    {
        "name": "calculate_margin",
        "description": "仕入れ価格(JPY)と販売価格(USD)から利益率を計算する。",
        "input_schema": {
            "type": "object",
            "properties": {
                "source_price_jpy": {
                    "type": "integer",
                    "description": "仕入れ価格（円）",
                },
                "sale_price_usd": {
                    "type": "number",
                    "description": "販売価格（USD）",
                },
                "shipping_cost_jpy": {
                    "type": "integer",
                    "description": "送料（円）",
                    "default": 2000,
                },
            },
            "required": ["source_price_jpy", "sale_price_usd"],
        },
    },
    # ── 出品更新 ──
    {
        "name": "update_listing",
        "description": "eBay出品を更新する（タイトル、説明文、価格、在庫数）。破壊的操作のため確認が必要。",
        "input_schema": {
            "type": "object",
            "properties": {
                "sku": {
                    "type": "string",
                    "description": "更新対象のSKU",
                },
                "title": {
                    "type": "string",
                    "description": "新しいタイトル",
                },
                "description": {
                    "type": "string",
                    "description": "新しい説明文",
                },
                "price_usd": {
                    "type": "number",
                    "description": "新しい価格（USD）",
                },
                "quantity": {
                    "type": "integer",
                    "description": "新しい在庫数",
                },
            },
            "required": ["sku"],
        },
    },
    # ── 競合価格モニター ──
    {
        "name": "run_price_monitor",
        "description": "全出品の競合価格を一括チェックする。価格差10%超のアイテムをアラートとして返す。",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "チェック対象の最大件数（API制限のため）",
                    "default": 20,
                },
            },
        },
    },
    # ── AI価格アドバイス ──
    {
        "name": "get_price_advice",
        "description": "指定SKUの競合価格データを元にAIが最適価格を提案する。事前にanalyze_pricingで価格データの取得が必要。",
        "input_schema": {
            "type": "object",
            "properties": {
                "sku": {
                    "type": "string",
                    "description": "価格提案対象のSKU",
                },
                "source_cost_jpy": {
                    "type": "integer",
                    "description": "仕入れ原価（円）。指定すると利益率も計算する。",
                },
            },
            "required": ["sku"],
        },
    },
    # ── 一括価格提案 ──
    {
        "name": "batch_price_advice",
        "description": "価格差が大きい出品に対して一括でAI価格提案を生成する。",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "分析対象の最大件数",
                    "default": 10,
                },
            },
        },
    },
    # ── 価格承認・適用 ──
    {
        "name": "apply_price_change",
        "description": "AI提案の価格変更をeBayに適用する。破壊的操作のため確認が必要。",
        "input_schema": {
            "type": "object",
            "properties": {
                "sku": {
                    "type": "string",
                    "description": "価格変更対象のSKU",
                },
                "new_price_usd": {
                    "type": "number",
                    "description": "新しい価格（USD）",
                },
            },
            "required": ["sku", "new_price_usd"],
        },
    },
    # ── ダッシュボード ──
    {
        "name": "get_dashboard_stats",
        "description": "ダッシュボード用の統計データを取得（出品数、在庫切れ、売上サマリー等）。",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    # ── Phase 3: 需要検知 ──
    {
        "name": "research_demand",
        "description": "指定カテゴリ/キーワードのeBay市場需要を分析する。売れ筋度、価格帯、推定利益率、有望商品リストを返す。",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "検索キーワード（英語）。例: 'vintage synthesizer', 'Nakamichi Dragon'",
                },
                "max_source_price_jpy": {
                    "type": "integer",
                    "description": "仕入れ上限（円）",
                    "default": 50000,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "compare_categories",
        "description": "複数カテゴリを比較分析し、最も有望な市場をランキングする。",
        "input_schema": {
            "type": "object",
            "properties": {
                "queries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "比較するキーワードリスト（英語）。例: ['vintage synthesizer', 'turntable', 'cassette deck']",
                },
            },
            "required": ["queries"],
        },
    },
    {
        "name": "run_research",
        "description": "AIリサーチエージェントに自然言語で市場調査を指示する。複数のツールを自律的に使い分けて包括的な分析レポートを生成する。",
        "input_schema": {
            "type": "object",
            "properties": {
                "instruction": {
                    "type": "string",
                    "description": "リサーチ指示（日本語OK）。例: 'ビンテージシンセサイザーで利益が出る商品を見つけて'",
                },
            },
            "required": ["instruction"],
        },
    },
    {
        "name": "generate_and_preview",
        "description": "リサーチ結果から出品ドラフトを生成し、プレビューを返す。AIが最適なタイトル・説明文・価格を提案する。",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_name": {
                    "type": "string",
                    "description": "商品名（ブランド名+モデル名）",
                },
                "target_price_usd": {
                    "type": "number",
                    "description": "目標販売価格（USD）",
                },
                "source_price_jpy": {
                    "type": "integer",
                    "description": "仕入れ価格（円）",
                },
                "condition": {
                    "type": "string",
                    "description": "商品状態",
                    "default": "Used - Good",
                },
                "category": {
                    "type": "string",
                    "description": "カテゴリ",
                    "default": "",
                },
            },
            "required": ["product_name"],
        },
    },
    # ── Phase 4: コミュニケーション＆分析 ──
    {
        "name": "sync_sales",
        "description": "eBayから最近の注文データを取得しDBに同期する。売上・利益データを最新化する。",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "取得期間（日数）",
                    "default": 30,
                },
            },
        },
    },
    {
        "name": "get_sales_analytics",
        "description": "売上分析データを取得する。日次推移、トップ商品、利益率を含む包括的なレポート。",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "分析期間（日数）",
                    "default": 30,
                },
            },
        },
    },
    {
        "name": "check_messages",
        "description": "eBayバイヤーからのメッセージを確認する。未読メッセージのリストを返す。",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "取得期間（日数）",
                    "default": 7,
                },
            },
        },
    },
    {
        "name": "draft_reply",
        "description": "バイヤーメッセージに対するAI返信ドラフトを生成する。送信前に人間確認必須。",
        "input_schema": {
            "type": "object",
            "properties": {
                "message_id": {
                    "type": "string",
                    "description": "返信対象のメッセージID",
                },
                "sender": {
                    "type": "string",
                    "description": "送信者",
                },
                "subject": {
                    "type": "string",
                    "description": "件名",
                },
                "body": {
                    "type": "string",
                    "description": "メッセージ本文",
                },
                "item_id": {
                    "type": "string",
                    "description": "関連アイテムID",
                    "default": "",
                },
            },
            "required": ["body"],
        },
    },
    {
        "name": "process_unread_messages",
        "description": "未読のバイヤーメッセージを一括取得し、全件の返信ドラフトを生成する。",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "取得期間（日数）",
                    "default": 7,
                },
            },
        },
    },
    # ── 仕入れ管理 ──
    {
        "name": "record_procurement",
        "description": "仕入れ実績を記録する。日本マーケットプレイスでの購入情報をDBに保存し、SKUと紐付けて原価管理する。",
        "input_schema": {
            "type": "object",
            "properties": {
                "sku": {
                    "type": "string",
                    "description": "紐付けるeBay SKU（出品前なら空文字可）",
                    "default": "",
                },
                "source_candidate_id": {
                    "type": "integer",
                    "description": "SourceCandidate ID（検索結果から購入した場合）",
                },
                "platform": {
                    "type": "string",
                    "description": "購入先（ヤフオク/メルカリ/PayPayフリマ/ラクマ/オフモール/その他）",
                },
                "title": {
                    "type": "string",
                    "description": "購入商品名",
                },
                "url": {
                    "type": "string",
                    "description": "購入ページURL",
                    "default": "",
                },
                "purchase_price_jpy": {
                    "type": "integer",
                    "description": "購入価格（円）",
                },
                "shipping_cost_jpy": {
                    "type": "integer",
                    "description": "送料（円）",
                    "default": 0,
                },
                "other_cost_jpy": {
                    "type": "integer",
                    "description": "その他費用（円）",
                    "default": 0,
                },
                "purchase_date": {
                    "type": "string",
                    "description": "購入日 (YYYY-MM-DD)",
                },
                "notes": {
                    "type": "string",
                    "description": "備考",
                },
            },
            "required": ["platform", "title", "purchase_price_jpy"],
        },
    },
    {
        "name": "update_procurement",
        "description": "仕入れ実績を更新する（ステータス変更、受取日記録、SKU紐付けなど）。",
        "input_schema": {
            "type": "object",
            "properties": {
                "procurement_id": {
                    "type": "integer",
                    "description": "更新対象の仕入れID",
                },
                "sku": {
                    "type": "string",
                    "description": "紐付けるSKU",
                },
                "status": {
                    "type": "string",
                    "description": "ステータス (purchased/shipped/received/listed)",
                },
                "received_date": {
                    "type": "string",
                    "description": "受取日 (YYYY-MM-DD)",
                },
                "shipping_cost_jpy": {
                    "type": "integer",
                    "description": "送料（判明後に更新）",
                },
                "notes": {
                    "type": "string",
                    "description": "備考",
                },
            },
            "required": ["procurement_id"],
        },
    },
    # ── Instagram ──
    {
        "name": "generate_instagram_post",
        "description": "eBay出品データからInstagram投稿キャプション・ハッシュタグを自動生成する。ドラフトとしてDBに保存される。",
        "input_schema": {
            "type": "object",
            "properties": {
                "sku": {
                    "type": "string",
                    "description": "eBay SKU",
                },
                "content_type": {
                    "type": "string",
                    "enum": ["carousel", "reel_script", "single", "story"],
                    "description": "投稿形式",
                    "default": "carousel",
                },
                "tone": {
                    "type": "string",
                    "enum": ["showcase", "educational", "behind_scenes", "urgency"],
                    "description": "投稿のトーン",
                    "default": "showcase",
                },
            },
            "required": ["sku"],
        },
    },
    {
        "name": "publish_instagram_post",
        "description": "[破壊的操作] 生成済みInstagramドラフトをMeta Graph API経由で投稿する。",
        "input_schema": {
            "type": "object",
            "properties": {
                "instagram_post_id": {
                    "type": "integer",
                    "description": "InstagramPost DB ID",
                },
                "schedule_at": {
                    "type": "string",
                    "description": "予約投稿日時 (ISO 8601形式)。省略時は即時投稿。",
                },
            },
            "required": ["instagram_post_id"],
        },
    },
    {
        "name": "get_instagram_analytics",
        "description": "Instagram投稿のパフォーマンス分析を取得する。投稿一覧・エンゲージメント・トレンドを返す。",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "分析期間（日数）",
                    "default": 30,
                },
            },
        },
    },
    {
        "name": "generate_dm_reply",
        "description": "Instagram DMの問合せに対するAI返信ドラフトを生成する。在庫マッチング・直接販売価格提示を含む。",
        "input_schema": {
            "type": "object",
            "properties": {
                "dm_text": {
                    "type": "string",
                    "description": "DMメッセージ本文",
                },
                "sender_name": {
                    "type": "string",
                    "description": "送信者名",
                    "default": "",
                },
                "context": {
                    "type": "string",
                    "description": "追加コンテキスト（関連商品SKU等）",
                    "default": "",
                },
            },
            "required": ["dm_text"],
        },
    },
    # ── カテゴリ Aspects ──
    {
        "name": "get_category_aspects",
        "description": "eBay Taxonomy APIでカテゴリの必須/推奨Item Specificsを取得する。出品時のItem Specifics設定に使用。",
        "input_schema": {
            "type": "object",
            "properties": {
                "category_id": {
                    "type": "string",
                    "description": "eBayカテゴリID（例: '38071' = Synthesizers）",
                },
            },
            "required": ["category_id"],
        },
    },
    # ── スプレッドシート読み取り ──
    {
        "name": "read_listing_sheet",
        "description": "Google Sheets/CSVから出品データを読み取る。リサーチスプレッドシートの商品名・カテゴリ・価格等を一覧取得。",
        "input_schema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "Google Sheets URL/ID、またはCSVファイルパス",
                },
                "sheet_name": {
                    "type": "string",
                    "description": "シート名（省略時は最初のシート）",
                    "default": "",
                },
            },
            "required": ["source"],
        },
    },
    # ── 新規出品（下書き） ──
    {
        "name": "create_draft_listing",
        "description": "1件の新規eBay出品を下書き状態で作成する。AIがタイトル・説明文・Item Specificsを生成し、eBayに下書き登録。",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_name": {
                    "type": "string",
                    "description": "商品名（ブランド名+モデル名）",
                },
                "price_usd": {
                    "type": "number",
                    "description": "販売価格（USD）",
                },
                "category_id": {
                    "type": "string",
                    "description": "eBayカテゴリID",
                },
                "condition": {
                    "type": "string",
                    "description": "状態 (NEW, USED_EXCELLENT, USED_VERY_GOOD, USED_GOOD等)",
                    "default": "USED_EXCELLENT",
                },
                "sku": {
                    "type": "string",
                    "description": "SKU（省略時は自動生成）",
                },
                "title": {
                    "type": "string",
                    "description": "出品タイトル（省略時はAI生成）",
                },
                "description": {
                    "type": "string",
                    "description": "説明文HTML（省略時はAI生成）",
                },
                "aspects": {
                    "type": "object",
                    "description": "Item Specifics（省略時はAI生成）",
                },
                "image_urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "商品画像URL（最大12枚）",
                    "default": [],
                },
            },
            "required": ["product_name", "price_usd", "category_id"],
        },
    },
    # ── バッチ出品（一括下書き） ──
    {
        "name": "batch_create_drafts",
        "description": "スプレッドシート/CSVから複数商品を一括で下書き登録する。「出品して」の中核機能。サマリーテーブルを返す。",
        "input_schema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "Google Sheets URL/ID、またはCSVファイルパス",
                },
                "sheet_name": {
                    "type": "string",
                    "description": "シート名（省略時は最初のシート）",
                    "default": "",
                },
                "row_numbers": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "出品する行番号リスト（省略時は全行）",
                    "default": [],
                },
            },
            "required": ["source"],
        },
    },
    # ── 下書き公開 ──
    {
        "name": "publish_draft_listings",
        "description": "[破壊的操作] 下書き状態のeBay出品を一括公開する。確認後「公開して」で使用。",
        "input_schema": {
            "type": "object",
            "properties": {
                "offer_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "公開するOffer IDリスト（省略時は全未公開を対象）",
                    "default": [],
                },
            },
        },
    },
    # ── 利益管理 ──
    {
        "name": "profit_summary",
        "description": "月別の利益サマリーを取得する。売上・経費・純利益・利益率を月単位で集計。「今月の利益は？」で使用。",
        "input_schema": {
            "type": "object",
            "properties": {
                "months": {
                    "type": "integer",
                    "description": "取得する月数",
                    "default": 3,
                },
            },
        },
    },
    {
        "name": "export_tax_report",
        "description": "税務申告用のCSVデータを生成する。売上明細(税理士用)・月次集計(確定申告用)・仕入明細(消費税還付用)の3種類。",
        "input_schema": {
            "type": "object",
            "properties": {
                "report_type": {
                    "type": "string",
                    "enum": ["sales", "monthly", "procurement"],
                    "description": "レポート種類: sales=売上明細, monthly=月次集計, procurement=仕入明細",
                    "default": "monthly",
                },
                "year": {
                    "type": "string",
                    "description": "対象年 (例: 2025)",
                    "default": "",
                },
            },
        },
    },
]

# 破壊的ツール（人間確認必須）
DESTRUCTIVE_TOOLS = {"update_listing", "apply_price_change", "publish_instagram_post", "publish_draft_listings"}
