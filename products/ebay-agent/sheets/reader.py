"""Google Sheets リーダー — リサーチスプレッドシートからデータ取得

出品フローで使用するスプレッドシートを読み取る。
gspread + サービスアカウント認証 or OAuth2。
フォールバック: CSV ファイル読み取り。

スプレッドシート想定カラム:
  行 | 商品名 | カテゴリNo | 販売価格(USD) | 送料プラン | 仕入れURL | eBay URL | コンディション | メモ
"""
from __future__ import annotations

import csv
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ListingRow:
    """スプレッドシート1行分のデータ"""
    row_number: int
    product_name: str
    category_id: str = ""
    price_usd: float = 0.0
    shipping_plan: str = ""
    source_url: str = ""
    ebay_url: str = ""
    condition: str = "USED_EXCELLENT"
    notes: str = ""
    source_price_jpy: int = 0
    image_urls: list[str] = field(default_factory=list)


# ── カラム名マッピング（日本語/英語の揺れ吸収） ────────────

COLUMN_MAP = {
    # 商品名
    "商品名": "product_name", "product_name": "product_name", "title": "product_name",
    "商品": "product_name", "name": "product_name",
    # カテゴリ
    "カテゴリno": "category_id", "カテゴリーno": "category_id",
    "category_id": "category_id", "category": "category_id",
    "カテゴリ": "category_id", "カテゴリー": "category_id",
    # 価格
    "販売価格": "price_usd", "販売価格(usd)": "price_usd", "price": "price_usd",
    "price_usd": "price_usd", "usd": "price_usd",
    # 送料
    "送料プラン": "shipping_plan", "shipping_plan": "shipping_plan", "shipping": "shipping_plan",
    # 仕入れURL
    "仕入れurl": "source_url", "source_url": "source_url", "仕入れ": "source_url",
    "仕入れリンク": "source_url",
    # eBay URL
    "ebay url": "ebay_url", "ebay_url": "ebay_url", "ebay": "ebay_url",
    "ebayリンク": "ebay_url",
    # コンディション
    "コンディション": "condition", "condition": "condition", "状態": "condition",
    # メモ
    "メモ": "notes", "notes": "notes", "備考": "notes",
    # 仕入れ価格
    "仕入れ価格": "source_price_jpy", "仕入れ価格(jpy)": "source_price_jpy",
    "source_price_jpy": "source_price_jpy", "cost": "source_price_jpy",
    "原価": "source_price_jpy",
    # 画像
    "画像url": "image_urls", "image_urls": "image_urls", "images": "image_urls",
}

# コンディション文字列の正規化
CONDITION_MAP = {
    "new": "NEW", "新品": "NEW",
    "like new": "LIKE_NEW", "ほぼ新品": "LIKE_NEW",
    "excellent": "USED_EXCELLENT", "非常に良い": "USED_EXCELLENT",
    "very good": "USED_VERY_GOOD", "良い": "USED_VERY_GOOD",
    "good": "USED_GOOD", "やや傷や汚れあり": "USED_GOOD",
    "acceptable": "USED_ACCEPTABLE", "傷や汚れあり": "USED_ACCEPTABLE",
    "for parts": "FOR_PARTS_OR_NOT_WORKING", "ジャンク": "FOR_PARTS_OR_NOT_WORKING",
}


def _normalize_condition(raw: str) -> str:
    """コンディション文字列を eBay API の enum に変換"""
    key = raw.strip().lower()
    return CONDITION_MAP.get(key, raw.upper() if raw.isupper() else "USED_EXCELLENT")


def _parse_row(row_number: int, row: dict) -> Optional[ListingRow]:
    """辞書形式の1行を ListingRow に変換"""
    mapped = {}
    for col_name, value in row.items():
        normalized_key = col_name.strip().lower()
        field_name = COLUMN_MAP.get(normalized_key)
        if field_name:
            mapped[field_name] = value

    product_name = mapped.get("product_name", "").strip()
    if not product_name:
        return None

    # 数値フィールド
    price_raw = mapped.get("price_usd", "0")
    try:
        price_usd = float(str(price_raw).replace("$", "").replace(",", "").strip() or "0")
    except ValueError:
        price_usd = 0.0

    source_price_raw = mapped.get("source_price_jpy", "0")
    try:
        source_price_jpy = int(float(str(source_price_raw).replace("¥", "").replace(",", "").strip() or "0"))
    except ValueError:
        source_price_jpy = 0

    # 画像URL（カンマ区切り or JSON配列）
    images_raw = mapped.get("image_urls", "")
    if isinstance(images_raw, list):
        image_urls = images_raw
    elif images_raw.startswith("["):
        try:
            image_urls = json.loads(images_raw)
        except json.JSONDecodeError:
            image_urls = []
    else:
        image_urls = [u.strip() for u in str(images_raw).split(",") if u.strip()]

    return ListingRow(
        row_number=row_number,
        product_name=product_name,
        category_id=str(mapped.get("category_id", "")).strip(),
        price_usd=price_usd,
        shipping_plan=str(mapped.get("shipping_plan", "")).strip(),
        source_url=str(mapped.get("source_url", "")).strip(),
        ebay_url=str(mapped.get("ebay_url", "")).strip(),
        condition=_normalize_condition(str(mapped.get("condition", ""))),
        notes=str(mapped.get("notes", "")).strip(),
        source_price_jpy=source_price_jpy,
        image_urls=image_urls,
    )


# ── Google Sheets 読み取り ────────────────────────────────

def read_google_sheet(spreadsheet_id: str, sheet_name: str = "", range_name: str = "") -> list[ListingRow]:
    """
    Google Sheets API でスプレッドシートを読み取る。
    gspread がインストールされている必要がある。

    認証方法:
      1. サービスアカウント JSON: GOOGLE_SERVICE_ACCOUNT_FILE 環境変数
      2. OAuth 認証: tokens/google_credentials.json
    """
    try:
        import gspread
    except ImportError:
        raise ImportError("gspread が未インストールです: pip install gspread")

    # 認証
    sa_file = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "")
    creds_file = os.environ.get(
        "GOOGLE_CREDENTIALS_FILE",
        str(Path(__file__).parent.parent / "tokens" / "google_credentials.json"),
    )

    if sa_file and Path(sa_file).exists():
        gc = gspread.service_account(filename=sa_file)
    elif Path(creds_file).exists():
        gc = gspread.oauth(credentials_filename=creds_file)
    else:
        raise FileNotFoundError(
            "Google認証ファイルが見つかりません。\n"
            "GOOGLE_SERVICE_ACCOUNT_FILE を設定するか、"
            "tokens/google_credentials.json を配置してください。"
        )

    spreadsheet = gc.open_by_key(spreadsheet_id)

    if sheet_name:
        worksheet = spreadsheet.worksheet(sheet_name)
    else:
        worksheet = spreadsheet.sheet1

    records = worksheet.get_all_records()
    rows = []
    for i, record in enumerate(records, start=2):  # ヘッダーが1行目なので2から
        row = _parse_row(i, record)
        if row:
            rows.append(row)

    logger.info(f"Google Sheets 読み取り完了: {len(rows)}行")
    return rows


# ── CSV 読み取り（フォールバック） ────────────────────────

def read_csv(file_path: str) -> list[ListingRow]:
    """CSVファイルを読み取ってListingRowリストを返す"""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"CSVファイルが見つかりません: {file_path}")

    rows = []
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for i, record in enumerate(reader, start=2):
            row = _parse_row(i, record)
            if row:
                rows.append(row)

    logger.info(f"CSV 読み取り完了: {len(rows)}行 ({file_path})")
    return rows


# ── 統合リーダー ─────────────────────────────────────────

def read_listing_data(source: str, sheet_name: str = "") -> list[ListingRow]:
    """
    ソースを自動判別して読み取る。

    source:
      - Google Sheet ID (44文字の英数字) → Google Sheets
      - Google Sheet URL → ID を抽出して Google Sheets
      - ファイルパス (.csv) → CSV
    """
    import re

    # Google Sheets URL パターン
    sheet_match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", source)
    if sheet_match:
        return read_google_sheet(sheet_match.group(1), sheet_name=sheet_name)

    # Google Sheet ID (44文字の英数字ハイフンアンダースコア)
    if re.match(r"^[a-zA-Z0-9_-]{20,}$", source) and not source.endswith(".csv"):
        return read_google_sheet(source, sheet_name=sheet_name)

    # CSV ファイル
    return read_csv(source)
