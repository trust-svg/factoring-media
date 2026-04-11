"""ツールハンドラー — 各ツール呼び出しの実処理

ツールレジストリで定義された各ツールの実装。
既存プロダクトのコードをラップして呼び出す。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from config import EBAY_FEE_RATE
from database.models import get_db, ShopifyConfig
from shopify.sync import get_discount_rate, get_shopify_price
from database import crud
from ebay_core.client import (
    get_active_listings,
    get_active_listings_trading,
    get_out_of_stock_items,
    search_ebay,
    update_listing as ebay_update_listing,
    get_category_aspects,
    create_inventory_item,
    create_offer,
    publish_offer,
    get_fulfillment_policies,
    get_return_policies,
    get_payment_policies,
)
from ebay_core.exchange_rate import get_usd_to_jpy, jpy_to_usd
from listing.generator import generate_listing

logger = logging.getLogger(__name__)


async def handle_tool_call(name: str, tool_input: dict[str, Any]) -> str:
    """ツール名とパラメータを受け取り、結果をJSON文字列で返す"""
    try:
        handler = HANDLERS.get(name)
        if not handler:
            return json.dumps({"error": f"Unknown tool: {name}"})
        result = await handler(tool_input)
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        logger.exception(f"Tool {name} failed")
        return json.dumps({"error": str(e)})


# ── 各ツール実装 ──────────────────────────────────────────

async def _check_inventory(params: dict) -> dict:
    out_of_stock_only = params.get("out_of_stock_only", False)
    if out_of_stock_only:
        items = get_out_of_stock_items()
    else:
        items = get_active_listings()

    # DBに同期
    db = get_db()
    try:
        for item in items:
            crud.upsert_listing(
                db,
                sku=item.sku,
                listing_id=item.listing_id,
                title=item.title,
                price_usd=item.price_usd,
                quantity=item.quantity,
                category_id=item.category_id,
                condition=item.condition,
                image_urls_json=json.dumps(item.image_urls),
                item_specifics_json=json.dumps(item.item_specifics),
                description=item.description,
                offer_id=item.offer_id,
            )
    finally:
        db.close()

    return {
        "total": len(items),
        "out_of_stock": sum(1 for i in items if i.is_out_of_stock),
        "items": [
            {
                "sku": i.sku,
                "title": i.title,
                "price_usd": i.price_usd,
                "quantity": i.quantity,
                "is_out_of_stock": i.is_out_of_stock,
            }
            for i in items[:50]  # 上限50件
        ],
    }


async def _search_sources(params: dict) -> dict:
    """日本マーケットプレイス検索（サイトレジストリ駆動・スコアリング・画像比較・型番フィルタ付き）

    仕入れ検索の3原則:
      1. 巡回先を絞る → site_registry の enabled サイトのみ巡回
      2. 読む情報を絞る → 統一スキーマ（タイトル・価格・コンディション・画像URL）のみ
      3. 画像判別を入れる → ebay_image_url でAI画像比較（デフォルトON）
    """
    import importlib
    from sourcing.scorer import pick_best_candidates
    from sourcing.site_registry import get_enabled_sites, SITE_REGISTRY

    keyword = params["keyword"]
    max_price = params.get("max_price_jpy", 50000)
    junk_ok = params.get("junk_ok", False)
    ebay_image_url = params.get("ebay_image_url", "")
    top_n = params.get("top_n", 5)
    sites_filter = params.get("sites", [])  # 特定サイトのみ指定可能

    # ── サイトレジストリから巡回先を決定 ──
    enabled_sites = get_enabled_sites()
    if sites_filter:
        enabled_sites = [s for s in enabled_sites if s["id"] in sites_filter]

    all_results = []
    errors = []
    sites_searched = []
    site_reliability = {}

    for site in enabled_sites:
        site_id = site["id"]
        display_name = site["display_name"]
        max_results = site["max_results"]
        scraper_class_path = site["scraper_class"]
        # reliability を display_name でも引けるように両方登録
        site_reliability[site_id] = site["reliability"]
        site_reliability[display_name] = site["reliability"]

        try:
            # scraper_class_path: "scrapers.offmall.OffmallScraper"
            module_path, class_name = scraper_class_path.rsplit(".", 1)
            module = importlib.import_module(module_path)
            scraper_cls = getattr(module, class_name)
            results = await scraper_cls().search(keyword, max_price, junk_ok, limit=max_results)
            all_results.extend(results)
            sites_searched.append({
                "id": site_id,
                "name": display_name,
                "results_count": len(results),
            })
            logger.info(f"  [{display_name}] {len(results)}件取得")
        except ImportError as e:
            errors.append(f"{display_name}: モジュール未実装 ({e})")
        except Exception as e:
            errors.append(f"{display_name}: {e}")
            logger.warning(f"{display_name}検索エラー: {e}")

    # ── 画像比較未指定の警告 ──
    image_warning = None
    if not ebay_image_url:
        image_warning = (
            "⚠ ebay_image_url が未指定です。画像比較なしでは別商品を拾いやすく、"
            "精度が大幅に低下します。eBay出品画像URLを指定してください。"
        )
        logger.warning(image_warning)

    # ── スコアリング＆フィルタリング（型番フィルタ・画像比較・プラットフォーム分散） ──
    best_candidates = pick_best_candidates(
        results=all_results,
        keyword=keyword,
        max_price_jpy=max_price,
        ebay_image_url=ebay_image_url,
        top_n=top_n,
        site_reliability=site_reliability,
    )

    # ── DB に保存（全結果） ──
    db = get_db()
    try:
        for r in all_results:
            crud.add_source_candidate(
                db,
                search_keyword=keyword,
                platform=r.platform,
                title=r.title,
                price_jpy=r.price_jpy,
                condition=r.condition,
                url=r.url,
                image_url=r.image_url,
                is_junk=int(r.is_junk),
            )
    finally:
        db.close()

    return {
        "keyword": keyword,
        "max_price_jpy": max_price,
        "junk_ok": junk_ok,
        "image_comparison": "enabled" if ebay_image_url else "disabled",
        "image_warning": image_warning,
        "total_raw": len(all_results),
        "total_scored": len(best_candidates),
        "sites_searched": sites_searched,
        "platforms_searched": len(sites_searched),
        "best_candidates": best_candidates,
        "all_candidates": [
            {
                "platform": r.platform,
                "title": r.title,
                "price_jpy": r.price_jpy,
                "condition": r.condition,
                "url": r.url,
                "image_url": r.image_url,
                "is_junk": r.is_junk,
            }
            for r in sorted(all_results, key=lambda r: r.price_jpy)[:30]
        ],
        "errors": errors if errors else None,
    }


async def _generate_listing(params: dict) -> dict:
    product_name = params["product_name"]
    category = params.get("category", "")
    condition = params.get("condition", "")
    keywords = params.get("competitor_keywords", [])

    result = await generate_listing(
        product_name=product_name,
        category=category,
        condition=condition,
        competitor_keywords=keywords,
    )
    return result


async def _analyze_seo(params: dict) -> dict:
    """SEOスコア分析（簡易版）"""
    sku = params["sku"]
    db = get_db()
    try:
        listing = crud.get_listing(db, sku)
        if not listing:
            return {"error": f"SKU {sku} が見つかりません"}

        # 簡易スコアリング
        title_len = len(listing.title)
        title_score = min(100, int(title_len / 80 * 100)) if title_len > 0 else 0

        desc_len = len(listing.description or "")
        desc_score = min(100, int(desc_len / 500 * 100))

        images = json.loads(listing.image_urls_json) if listing.image_urls_json else []
        photo_score = min(100, len(images) * 20)

        specifics = json.loads(listing.item_specifics_json) if listing.item_specifics_json else {}
        specifics_score = min(100, len(specifics) * 12)

        overall = int(
            title_score * 0.35
            + desc_score * 0.25
            + specifics_score * 0.25
            + photo_score * 0.15
        )

        issues = []
        if title_len < 60:
            issues.append(f"タイトルが短すぎます ({title_len}文字 / 推奨75-80文字)")
        if not listing.title.upper().endswith("JAPAN"):
            issues.append("タイトルが 'JAPAN' で終わっていません")
        if desc_len < 200:
            issues.append(f"説明文が短すぎます ({desc_len}文字 / 推奨200文字以上)")
        if len(images) < 5:
            issues.append(f"写真が少なすぎます ({len(images)}枚 / 推奨5枚以上)")
        if len(specifics) < 5:
            issues.append(f"Item Specificsが少なすぎます ({len(specifics)}項目 / 推奨8項目以上)")

        return {
            "sku": sku,
            "title": listing.title,
            "overall_score": overall,
            "title_score": title_score,
            "description_score": desc_score,
            "specifics_score": specifics_score,
            "photo_score": photo_score,
            "issues": issues,
        }
    finally:
        db.close()


async def _optimize_listing(params: dict) -> dict:
    """AI出品最適化（Claude tool_use）"""
    from listing.prompts import SEO_OPTIMIZER_SYSTEM_PROMPT
    import anthropic

    sku = params["sku"]
    seo_data = await _analyze_seo({"sku": sku})
    if "error" in seo_data:
        return seo_data

    db = get_db()
    try:
        listing = crud.get_listing(db, sku)
        if not listing:
            return {"error": f"SKU {sku} が見つかりません"}

        client = anthropic.Anthropic()
        prompt = f"""Optimize this eBay listing for better search visibility and sales.

CURRENT LISTING:
- Title ({len(listing.title)} chars): "{listing.title}"
- Price: ${listing.price_usd:.2f}
- Condition: {listing.condition}
- SEO Score: {seo_data['overall_score']}/100

Issues: {', '.join(seo_data['issues'])}

Please suggest optimized title (max 80 chars) and description improvements."""

        optimizer_tools = [
            {
                "name": "suggest_title",
                "description": "Suggest optimized title (max 80 chars)",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "new_title": {"type": "string", "maxLength": 80},
                        "reasoning": {"type": "string"},
                    },
                    "required": ["new_title", "reasoning"],
                },
            },
            {
                "name": "suggest_description",
                "description": "Suggest optimized description",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "new_description": {"type": "string"},
                        "reasoning": {"type": "string"},
                    },
                    "required": ["new_description", "reasoning"],
                },
            },
        ]

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            system=SEO_OPTIMIZER_SYSTEM_PROMPT,
            tools=optimizer_tools,
            messages=[{"role": "user", "content": prompt}],
        )

        result = {
            "sku": sku,
            "original_title": listing.title,
            "suggested_title": listing.title,
            "suggested_description": None,
            "reasoning": "",
        }

        for block in response.content:
            if block.type == "tool_use":
                if block.name == "suggest_title":
                    result["suggested_title"] = block.input.get("new_title", "")
                    result["reasoning"] += f"Title: {block.input.get('reasoning', '')}\n"
                elif block.name == "suggest_description":
                    result["suggested_description"] = block.input.get("new_description", "")
                    result["reasoning"] += f"Description: {block.input.get('reasoning', '')}\n"

        # DBに保存
        crud.add_optimization(
            db,
            sku=sku,
            original_title=listing.title,
            suggested_title=result["suggested_title"],
            original_description=listing.description,
            suggested_description=result["suggested_description"],
            reasoning=result["reasoning"],
            confidence=0.8 if result["suggested_title"] != listing.title else 0.3,
        )

        return result
    finally:
        db.close()


async def _search_ebay_handler(params: dict) -> dict:
    query = params["query"]
    limit = params.get("limit", 20)
    results = search_ebay(query, limit=limit)
    return {
        "query": query,
        "count": len(results),
        "results": results,
    }


async def _analyze_pricing(params: dict) -> dict:
    """競合価格分析"""
    sku = params["sku"]
    db = get_db()
    try:
        listing = crud.get_listing(db, sku)
        if not listing:
            return {"error": f"SKU {sku} が見つかりません"}

        # 競合検索
        competitors = search_ebay(listing.title, limit=20)
        if not competitors:
            return {"error": "競合データが取得できませんでした"}

        prices = [c["price"] for c in competitors if c["price"] > 0]
        if not prices:
            return {"error": "競合価格データなし"}

        avg_price = sum(prices) / len(prices)
        min_price = min(prices)
        max_price = max(prices)
        rate = get_usd_to_jpy()

        # 価格履歴に記録
        crud.add_price_history(
            db,
            sku=sku,
            our_price_usd=listing.price_usd,
            avg_competitor_price_usd=round(avg_price, 2),
            lowest_competitor_price_usd=round(min_price, 2),
            num_competitors=len(prices),
            exchange_rate=rate,
        )

        diff_pct = ((listing.price_usd - avg_price) / avg_price * 100) if avg_price else 0

        return {
            "sku": sku,
            "our_price_usd": listing.price_usd,
            "competitor_count": len(prices),
            "avg_competitor_price_usd": round(avg_price, 2),
            "min_competitor_price_usd": round(min_price, 2),
            "max_competitor_price_usd": round(max_price, 2),
            "price_diff_pct": round(diff_pct, 1),
            "exchange_rate": rate,
            "recommendation": (
                "価格は競合平均より安い — 値上げ余地あり" if diff_pct < -5
                else "価格は競合平均より高い — 値下げ検討" if diff_pct > 10
                else "価格は競合と適正範囲内"
            ),
        }
    finally:
        db.close()


async def _get_exchange_rate(params: dict) -> dict:
    rate = get_usd_to_jpy()
    return {
        "usd_to_jpy": rate,
        "example": f"$100 USD = ¥{int(100 * rate):,} JPY",
    }


async def _calculate_margin(params: dict) -> dict:
    source_jpy = params["source_price_jpy"]
    sale_usd = params["sale_price_usd"]
    shipping_jpy = params.get("shipping_cost_jpy", 2000)
    rate = get_usd_to_jpy()

    ebay_fees = sale_usd * EBAY_FEE_RATE
    total_cost_jpy = source_jpy + shipping_jpy
    total_cost_usd = jpy_to_usd(total_cost_jpy)
    profit_usd = sale_usd - ebay_fees - total_cost_usd
    margin_pct = (profit_usd / sale_usd * 100) if sale_usd else 0

    return {
        "sale_price_usd": sale_usd,
        "source_cost_jpy": source_jpy,
        "shipping_cost_jpy": shipping_jpy,
        "total_cost_usd": round(total_cost_usd, 2),
        "ebay_fees_usd": round(ebay_fees, 2),
        "profit_usd": round(profit_usd, 2),
        "margin_pct": round(margin_pct, 1),
        "exchange_rate": rate,
        "profitable": profit_usd > 0,
    }


async def _update_listing_handler(params: dict) -> dict:
    sku = params["sku"]
    updates = {}
    if "title" in params:
        updates["title"] = params["title"]
    if "description" in params:
        updates["description"] = params["description"]
    if "price_usd" in params:
        updates["price_usd"] = params["price_usd"]
    if "quantity" in params:
        updates["quantity"] = params["quantity"]

    if not updates:
        return {"error": "更新フィールドが指定されていません"}

    result = ebay_update_listing(sku, updates)

    # Shopify価格を連動更新（price_usdが変更された場合のみ）
    if result["success"] and "price_usd" in params:
        new_price = params["price_usd"]
        db_check = get_db()
        try:
            from database.models import Listing
            listing_obj = db_check.query(Listing).filter_by(sku=sku).first()
            if listing_obj and listing_obj.shopify_variant_id:
                discount_rate = get_discount_rate(db_check)
                shopify_price = get_shopify_price(new_price, discount_rate)
                try:
                    from shopify.client import ShopifyClient
                    client = ShopifyClient()
                    await client.update_variant_price(listing_obj.shopify_variant_id, shopify_price)
                    logger.info(f"Synced Shopify price for {sku}: ${shopify_price:.2f}")
                except Exception:
                    logger.warning(f"Failed to sync Shopify price for {sku}")
        finally:
            db_check.close()

    # 変更履歴を記録
    if result["success"]:
        db = get_db()
        try:
            for change in result["changes"]:
                field, _, value = change.partition(" -> ")
                crud.log_change(db, sku, field.strip(), "", value.strip())
        finally:
            db.close()

    return result


async def _get_dashboard_stats(params: dict) -> dict:
    db = get_db()
    try:
        return crud.get_dashboard_stats(db)
    finally:
        db.close()


# ── Phase 2: 価格インテリジェンス ────────────────────────

async def _run_price_monitor(params: dict) -> dict:
    from pricing.monitor import run_price_monitor
    limit = params.get("limit", 20)
    return run_price_monitor(limit=limit)


async def _get_price_advice(params: dict) -> dict:
    from pricing.advisor import get_price_advice
    sku = params["sku"]
    source_cost_jpy = params.get("source_cost_jpy")
    return await get_price_advice(sku, source_cost_jpy=source_cost_jpy)


async def _batch_price_advice(params: dict) -> dict:
    from pricing.advisor import batch_price_advice
    limit = params.get("limit", 10)
    return await batch_price_advice(limit=limit)


async def _apply_price_change(params: dict) -> dict:
    sku = params["sku"]
    new_price = params["new_price_usd"]

    db = get_db()
    try:
        listing = crud.get_listing(db, sku)
        if not listing:
            return {"error": f"SKU {sku} が見つかりません"}

        old_price = listing.price_usd
        result = ebay_update_listing(sku, {"price_usd": new_price})

        if result["success"]:
            crud.log_change(db, sku, "price", f"${old_price:.2f}", f"${new_price:.2f}")
            # DB内の価格も更新
            listing.price_usd = new_price
            db.commit()
            return {
                "success": True,
                "sku": sku,
                "old_price": old_price,
                "new_price": new_price,
                "change_pct": round((new_price - old_price) / old_price * 100, 1) if old_price else 0,
            }
        else:
            crud.log_change(db, sku, "price", f"${old_price:.2f}", f"${new_price:.2f}",
                           success=False, error=result.get("error", ""))
            return result
    finally:
        db.close()


# ── Phase 3: 需要検知・リサーチ ──────────────────────────

async def _research_demand(params: dict) -> dict:
    from research.demand import analyze_demand
    return analyze_demand(
        query=params["query"],
        max_source_price_jpy=params.get("max_source_price_jpy", 50000),
    )


async def _compare_categories(params: dict) -> dict:
    from research.demand import compare_categories
    return compare_categories(queries=params["queries"])


async def _run_research(params: dict) -> dict:
    from research.agent import run_research_agent
    return await run_research_agent(params["instruction"])


async def _generate_and_preview(params: dict) -> dict:
    """リサーチ→出品ドラフト生成パイプライン"""
    product_name = params["product_name"]
    target_price = params.get("target_price_usd")
    source_price = params.get("source_price_jpy")
    condition = params.get("condition", "Used - Good")
    category = params.get("category", "")

    # 1) 出品コンテンツ生成
    listing_result = await _generate_listing({
        "product_name": product_name,
        "category": category,
        "condition": condition,
    })

    # 2) 利益率計算（仕入れ価格が指定された場合）
    margin_data = None
    if source_price and target_price:
        margin_data = await _calculate_margin({
            "source_price_jpy": source_price,
            "sale_price_usd": target_price,
        })

    # 3) 競合価格チェック
    competitor_data = search_ebay(product_name, limit=10)
    competitor_prices = [c["price"] for c in competitor_data if c["price"] > 0]

    return {
        "product_name": product_name,
        "listing_draft": listing_result,
        "target_price_usd": target_price,
        "source_price_jpy": source_price,
        "condition": condition,
        "margin_analysis": margin_data,
        "competitor_prices": {
            "count": len(competitor_prices),
            "avg": round(sum(competitor_prices) / len(competitor_prices), 2) if competitor_prices else 0,
            "min": min(competitor_prices) if competitor_prices else 0,
            "max": max(competitor_prices) if competitor_prices else 0,
        },
        "status": "draft_ready",
        "note": "出品ドラフトが準備できました。内容を確認してeBayへの出品を承認してください。",
    }


# ── Phase 4: コミュニケーション＆分析 ─────────────────────

async def _sync_sales(params: dict) -> dict:
    from comms.sales_analytics import sync_sales_data
    return sync_sales_data(days=params.get("days", 30))


async def _get_sales_analytics(params: dict) -> dict:
    from comms.sales_analytics import get_sales_analytics
    return get_sales_analytics(days=params.get("days", 30))


async def _check_messages(params: dict) -> dict:
    from ebay_core.client import get_buyer_messages
    messages = get_buyer_messages(days=params.get("days", 7))
    unread = [m for m in messages if not m["is_read"]]
    return {
        "total": len(messages),
        "unread": len(unread),
        "messages": messages[:20],
    }


async def _draft_reply(params: dict) -> dict:
    from comms.buyer_messages import generate_reply_draft
    return await generate_reply_draft(params)


async def _process_unread_messages(params: dict) -> dict:
    from comms.buyer_messages import process_unread_messages
    return await process_unread_messages(days=params.get("days", 7))


# ── 仕入れ管理 ────────────────────────────────────────────

async def _record_procurement(params: dict) -> dict:
    """仕入れ実績を記録"""
    from datetime import datetime as dt
    db = get_db()
    try:
        purchase_date = None
        if params.get("purchase_date"):
            purchase_date = dt.strptime(params["purchase_date"], "%Y-%m-%d")

        proc = crud.add_procurement(
            db,
            sku=params.get("sku", ""),
            source_candidate_id=params.get("source_candidate_id"),
            platform=params["platform"],
            title=params["title"],
            url=params.get("url", ""),
            purchase_price_jpy=params["purchase_price_jpy"],
            shipping_cost_jpy=params.get("shipping_cost_jpy", 0),
            other_cost_jpy=params.get("other_cost_jpy", 0),
            purchase_date=purchase_date,
            notes=params.get("notes"),
        )

        # SourceCandidate のステータスも更新
        if params.get("source_candidate_id"):
            crud.update_candidate_status(db, params["source_candidate_id"], "purchased")

        return {
            "id": proc.id,
            "sku": proc.sku,
            "total_cost_jpy": proc.total_cost_jpy,
            "status": proc.status,
            "message": f"仕入れ記録を保存しました (ID: {proc.id}, 合計: ¥{proc.total_cost_jpy:,})",
        }
    finally:
        db.close()


async def _update_procurement(params: dict) -> dict:
    """仕入れ実績を更新"""
    from datetime import datetime as dt
    db = get_db()
    try:
        update_kwargs = {}
        for key in ["sku", "status", "shipping_cost_jpy", "notes"]:
            if key in params:
                update_kwargs[key] = params[key]
        if params.get("received_date"):
            update_kwargs["received_date"] = dt.strptime(params["received_date"], "%Y-%m-%d")

        proc = crud.update_procurement(db, params["procurement_id"], **update_kwargs)
        if not proc:
            return {"error": f"仕入れ ID {params['procurement_id']} が見つかりません"}

        return {
            "id": proc.id,
            "sku": proc.sku,
            "status": proc.status,
            "total_cost_jpy": proc.total_cost_jpy,
            "message": f"仕入れ ID {proc.id} を更新しました (ステータス: {proc.status})",
        }
    finally:
        db.close()


# ── Instagram ──────────────────────────────────────────────

async def _generate_instagram_post(params: dict) -> dict:
    from instagram.content_generator import generate_instagram_content
    return await generate_instagram_content(
        sku=params["sku"],
        content_type=params.get("content_type", "carousel"),
        tone=params.get("tone", "showcase"),
    )


async def _publish_instagram_post(params: dict) -> dict:
    """Instagram投稿を公開する"""
    from datetime import datetime as dt
    from instagram.client import InstagramClient
    from database.models import InstagramPost

    post_id = params["instagram_post_id"]
    schedule_at = params.get("schedule_at")

    db = get_db()
    try:
        post = db.query(InstagramPost).filter(InstagramPost.id == post_id).first()
        if not post:
            return {"error": f"Instagram投稿 ID {post_id} が見つかりません"}
        if post.status == "published":
            return {"error": "この投稿は既に公開済みです"}

        # 予約投稿の場合
        if schedule_at:
            post.scheduled_at = dt.fromisoformat(schedule_at)
            post.status = "scheduled"
            db.commit()
            return {
                "id": post.id,
                "status": "scheduled",
                "scheduled_at": schedule_at,
                "message": f"投稿を {schedule_at} に予約しました",
            }

        # 即時投稿
        client = InstagramClient()
        images = json.loads(post.image_urls_json) if post.image_urls_json else []
        hashtags = json.loads(post.hashtags_json) if post.hashtags_json else []
        full_caption = post.caption + "\n\n" + " ".join(f"#{tag}" for tag in hashtags)

        if not images:
            return {"error": "投稿する画像がありません"}

        if post.content_type == "carousel" and len(images) > 1:
            child_ids = []
            for img_url in images[:10]:
                cid = client.create_media_container(img_url, "", is_carousel_item=True)
                child_ids.append(cid)
            container_id = client.create_carousel_container(child_ids, full_caption)
        else:
            container_id = client.create_media_container(images[0], full_caption)

        ig_post_id = client.publish_media(container_id)

        post.ig_post_id = ig_post_id
        post.status = "published"
        post.published_at = dt.utcnow()
        db.commit()

        return {
            "id": post.id,
            "ig_post_id": ig_post_id,
            "status": "published",
            "mock": not client.is_connected,
            "message": f"Instagram投稿を公開しました (ID: {ig_post_id})",
        }
    finally:
        db.close()


async def _get_instagram_analytics(params: dict) -> dict:
    """Instagram投稿のパフォーマンス分析"""
    from datetime import datetime as dt, timedelta
    from database.models import InstagramPost

    days = params.get("days", 30)
    db = get_db()
    try:
        cutoff = dt.utcnow() - timedelta(days=days)
        posts = (
            db.query(InstagramPost)
            .filter(InstagramPost.created_at >= cutoff)
            .order_by(InstagramPost.created_at.desc())
            .all()
        )

        draft_count = sum(1 for p in posts if p.status == "draft")
        scheduled_count = sum(1 for p in posts if p.status == "scheduled")
        published_count = sum(1 for p in posts if p.status == "published")
        total_impressions = sum(p.impressions for p in posts)
        total_likes = sum(p.likes for p in posts)
        total_saves = sum(p.saves for p in posts)
        total_comments = sum(p.comments for p in posts)

        return {
            "period_days": days,
            "total_posts": len(posts),
            "draft": draft_count,
            "scheduled": scheduled_count,
            "published": published_count,
            "total_impressions": total_impressions,
            "total_likes": total_likes,
            "total_saves": total_saves,
            "total_comments": total_comments,
            "avg_engagement": round(
                (total_likes + total_saves + total_comments) / published_count, 1
            ) if published_count else 0,
            "posts": [
                {
                    "id": p.id,
                    "sku": p.sku,
                    "content_type": p.content_type,
                    "tone": p.tone,
                    "status": p.status,
                    "caption_preview": p.caption[:100] + "..." if len(p.caption) > 100 else p.caption,
                    "impressions": p.impressions,
                    "likes": p.likes,
                    "saves": p.saves,
                    "comments": p.comments,
                    "created_at": p.created_at.isoformat(),
                    "published_at": p.published_at.isoformat() if p.published_at else None,
                }
                for p in posts[:50]
            ],
        }
    finally:
        db.close()


async def _generate_dm_reply_handler(params: dict) -> dict:
    from instagram.dm_handler import generate_dm_reply
    return await generate_dm_reply(
        dm_text=params["dm_text"],
        sender_name=params.get("sender_name", ""),
        context=params.get("context", ""),
    )


# ── 出品作成（バッチ対応） ────────────────────────────────

async def _get_category_aspects_handler(params: dict) -> dict:
    """カテゴリの必須/推奨 Item Specifics を取得"""
    category_id = params["category_id"]
    return get_category_aspects(category_id)


async def _read_listing_sheet(params: dict) -> dict:
    """スプレッドシート/CSVから出品データを読み取る"""
    from sheets.reader import read_listing_data
    source = params["source"]
    sheet_name = params.get("sheet_name", "")

    try:
        rows = read_listing_data(source, sheet_name=sheet_name)
    except ImportError as e:
        return {"error": str(e)}
    except FileNotFoundError as e:
        return {"error": str(e)}

    return {
        "source": source,
        "total_rows": len(rows),
        "rows": [
            {
                "row": r.row_number,
                "product_name": r.product_name,
                "category_id": r.category_id,
                "price_usd": r.price_usd,
                "condition": r.condition,
                "source_url": r.source_url,
                "ebay_url": r.ebay_url,
                "source_price_jpy": r.source_price_jpy,
                "notes": r.notes,
            }
            for r in rows
        ],
    }


async def _create_draft_listing(params: dict) -> dict:
    """
    1件の新規出品を下書き作成する。
    InventoryItem作成 → Offer作成（未公開状態）
    """
    import uuid

    sku = params.get("sku") or f"ITEM-{uuid.uuid4().hex[:8].upper()}"
    product_name = params["product_name"]
    price_usd = params["price_usd"]
    category_id = params["category_id"]
    condition = params.get("condition", "USED_EXCELLENT")
    description = params.get("description", "")
    aspects = params.get("aspects", {})
    image_urls = params.get("image_urls", [])

    # 1) AI生成が必要な場合
    if not description or not aspects:
        listing_data = await _generate_listing({
            "product_name": product_name,
            "category": category_id,
            "condition": condition,
        })
        if not description:
            description = listing_data.get("description_html", "")
        if not aspects:
            aspects = {k: [v] if isinstance(v, str) else v for k, v in listing_data.get("specs", {}).items()}

    title = params.get("title", "")
    if not title:
        # AI生成タイトルを使用（最初のバリアント）
        listing_data = await _generate_listing({
            "product_name": product_name,
            "category": category_id,
            "condition": condition,
        })
        titles = listing_data.get("titles", [])
        title = titles[0] if titles else product_name

    # 2) Inventory Item 作成
    inv_result = create_inventory_item(
        sku=sku,
        product={
            "title": title,
            "description": description,
            "aspects": aspects,
            "imageUrls": image_urls,
        },
        condition=condition,
        quantity=1,
    )
    if not inv_result.get("success"):
        return {"success": False, "sku": sku, "error": inv_result.get("error", "Inventory作成失敗")}

    # 3) Offer 作成（ビジネスポリシーを自動取得）
    fulfillment_policies = get_fulfillment_policies()
    return_policies = get_return_policies()
    payment_policies = get_payment_policies()

    offer_result = create_offer(
        sku=sku,
        category_id=category_id,
        price_usd=price_usd,
        condition=condition,
        fulfillment_policy_id=fulfillment_policies[0]["id"] if fulfillment_policies else "",
        return_policy_id=return_policies[0]["id"] if return_policies else "",
        payment_policy_id=payment_policies[0]["id"] if payment_policies else "",
        listing_description=description,
    )
    if not offer_result.get("success"):
        return {"success": False, "sku": sku, "error": offer_result.get("error", "Offer作成失敗")}

    # 4) DB に記録
    db = get_db()
    try:
        crud.upsert_listing(
            db,
            sku=sku,
            listing_id="",
            title=title,
            price_usd=price_usd,
            quantity=1,
            category_id=category_id,
            condition=condition,
            image_urls_json=json.dumps(image_urls),
            item_specifics_json=json.dumps(aspects),
            description=description,
            offer_id=offer_result.get("offer_id", ""),
        )
    finally:
        db.close()

    return {
        "success": True,
        "sku": sku,
        "title": title,
        "price_usd": price_usd,
        "offer_id": offer_result.get("offer_id", ""),
        "status": "draft",
        "message": f"下書き作成完了: {title[:50]}... (${price_usd})",
    }


async def _batch_create_drafts(params: dict) -> dict:
    """
    スプレッドシート/CSVから複数商品を一括で下書き登録する。
    投稿画像のように「全N件の下書き登録が完了しました」＋サマリーテーブルを返す。
    """
    from sheets.reader import read_listing_data

    source = params["source"]
    sheet_name = params.get("sheet_name", "")
    row_numbers = params.get("row_numbers", [])  # 空なら全行

    try:
        rows = read_listing_data(source, sheet_name=sheet_name)
    except Exception as e:
        return {"error": str(e)}

    if row_numbers:
        rows = [r for r in rows if r.row_number in row_numbers]

    if not rows:
        return {"error": "出品データが見つかりません"}

    results = []
    success_count = 0
    error_count = 0

    for row in rows:
        try:
            result = await _create_draft_listing({
                "product_name": row.product_name,
                "price_usd": row.price_usd,
                "category_id": row.category_id,
                "condition": row.condition,
                "image_urls": row.image_urls,
            })
            results.append({
                "row": row.row_number,
                "product_name": row.product_name,
                "price_usd": row.price_usd,
                "sku": result.get("sku", ""),
                "offer_id": result.get("offer_id", ""),
                "success": result.get("success", False),
                "error": result.get("error"),
            })
            if result.get("success"):
                success_count += 1
            else:
                error_count += 1
        except Exception as e:
            results.append({
                "row": row.row_number,
                "product_name": row.product_name,
                "price_usd": row.price_usd,
                "success": False,
                "error": str(e),
            })
            error_count += 1

    return {
        "total": len(results),
        "success": success_count,
        "errors": error_count,
        "results": results,
        "message": f"全{success_count}件の下書き登録が完了しました。" + (
            f"（{error_count}件エラー）" if error_count else ""
        ),
        "next_step": "eBay Seller Hub（スケジュール済みリスト）で内容をご確認ください。確認後「公開して」と指示いただければ順次出品を開始します。",
    }


async def _publish_draft_listings(params: dict) -> dict:
    """
    下書き状態の Offer を一括公開する。
    offer_ids を指定するか、DBから未公開のものを自動取得。
    """
    offer_ids = params.get("offer_ids", [])

    if not offer_ids:
        # DBから未公開（listing_id が空）の offer を取得
        db = get_db()
        try:
            from database.models import Listing
            drafts = db.query(Listing).filter(
                Listing.offer_id != "",
                Listing.listing_id == "",
            ).all()
            offer_ids = [d.offer_id for d in drafts if d.offer_id]
        finally:
            db.close()

    if not offer_ids:
        return {"error": "公開する下書きが見つかりません"}

    results = []
    success_count = 0

    for offer_id in offer_ids:
        pub_result = publish_offer(offer_id)
        success = pub_result.get("success", False)
        listing_id = pub_result.get("listing_id", "")

        if success:
            success_count += 1
            # DB 更新
            db = get_db()
            try:
                from database.models import Listing
                listing = db.query(Listing).filter(Listing.offer_id == offer_id).first()
                if listing:
                    listing.listing_id = listing_id
                    db.commit()
            finally:
                db.close()

        results.append({
            "offer_id": offer_id,
            "listing_id": listing_id,
            "success": success,
            "error": pub_result.get("error") if not success else None,
        })

    return {
        "total": len(results),
        "published": success_count,
        "results": results,
        "message": f"全{success_count}件の出品を公開しました。",
    }


# ── 利益管理 ────────────────────────────────────────────

async def _profit_summary(params: dict) -> dict:
    """月別利益サマリー"""
    months = params.get("months", 3)
    db = get_db()
    try:
        summary = crud.get_profit_summary(db, months=months)
        return {"months": months, "summary": summary, "count": len(summary)}
    finally:
        db.close()


async def _export_tax_report(params: dict) -> dict:
    """税務レポート用データ生成（ダッシュボードのCSVエクスポートへ誘導）"""
    report_type = params.get("report_type", "monthly")
    year = params.get("year", "")
    base_url = f"/api/export/tax-report?type={report_type}"
    if year:
        base_url += f"&year={year}"
    return {
        "message": f"税務レポートが準備できました。以下のURLからCSVをダウンロードしてください。",
        "download_url": base_url,
        "report_type": report_type,
        "year": year or "全期間",
        "note": "ダッシュボードの利益管理ページ（/profit）からもエクスポートできます。",
    }


async def _expand_categories(params: dict) -> dict:
    """カテゴリ自動拡張パイプラインを実行"""
    from research.category_expansion import run_category_expansion_pipeline
    return await run_category_expansion_pipeline(
        notify=params.get("notify", True),
        auto_source=params.get("auto_source", True),
        top_n=params.get("top_n", 3),
    )


# ── Shopify連携 ──────────────────────────────────────────

async def _sync_all_to_shopify(params: dict) -> dict:
    from shopify.sync import push_all_unsynced
    result = await push_all_unsynced()
    return {
        "message": f"Shopify同期完了: 成功 {result['success']}件、失敗 {result['failed']}件",
        **result,
    }


async def _set_shopify_discount(params: dict) -> dict:
    discount_rate = float(params["discount_rate"])
    if not (0.0 <= discount_rate <= 1.0):
        return {"error": "discount_rate は0〜1の範囲で指定してください"}
    db = get_db()
    try:
        config = db.query(ShopifyConfig).filter_by(key="discount_rate").first()
        if config:
            config.value = str(discount_rate)
            config.updated_at = datetime.utcnow()
        else:
            db.add(ShopifyConfig(key="discount_rate", value=str(discount_rate), updated_at=datetime.utcnow()))
        db.commit()
        return {"message": f"Shopify割引率を {discount_rate*100:.1f}% に変更しました", "discount_rate": discount_rate}
    finally:
        db.close()


async def _get_shopify_status(params: dict) -> dict:
    from database.models import Listing
    db = get_db()
    try:
        synced = db.query(Listing).filter(Listing.shopify_product_id.isnot(None)).count()
        unsynced = db.query(Listing).filter(
            Listing.shopify_product_id.is_(None),
            Listing.quantity > 0,
        ).count()
        discount_rate = get_discount_rate(db)
        return {
            "synced": synced,
            "unsynced": unsynced,
            "discount_rate": discount_rate,
            "discount_pct": f"{discount_rate*100:.1f}%",
        }
    finally:
        db.close()


async def _remove_from_shopify(params: dict) -> dict:
    sku = params["sku"]
    from database.models import Listing
    from shopify.client import ShopifyClient
    db = get_db()
    try:
        listing = db.query(Listing).filter_by(sku=sku).first()
        if not listing:
            return {"error": f"SKU {sku} が見つかりません"}
        if not listing.shopify_product_id:
            return {"error": f"SKU {sku} はShopifyに同期されていません"}
        client = ShopifyClient()
        await client.delete_product(listing.shopify_product_id)
        listing.shopify_product_id = None
        listing.shopify_variant_id = None
        db.commit()
        return {"message": f"SKU {sku} をShopifyから削除しました"}
    finally:
        db.close()


# ── ハンドラーマッピング ──────────────────────────────────

HANDLERS = {
    "check_inventory": _check_inventory,
    "search_sources": _search_sources,
    "generate_listing": _generate_listing,
    "analyze_seo": _analyze_seo,
    "optimize_listing": _optimize_listing,
    "search_ebay": _search_ebay_handler,
    "analyze_pricing": _analyze_pricing,
    "get_exchange_rate": _get_exchange_rate,
    "calculate_margin": _calculate_margin,
    "update_listing": _update_listing_handler,
    "get_dashboard_stats": _get_dashboard_stats,
    # Phase 2
    "run_price_monitor": _run_price_monitor,
    "get_price_advice": _get_price_advice,
    "batch_price_advice": _batch_price_advice,
    "apply_price_change": _apply_price_change,
    # Phase 3
    "research_demand": _research_demand,
    "compare_categories": _compare_categories,
    "run_research": _run_research,
    "generate_and_preview": _generate_and_preview,
    # Phase 4
    "sync_sales": _sync_sales,
    "get_sales_analytics": _get_sales_analytics,
    "check_messages": _check_messages,
    "draft_reply": _draft_reply,
    "process_unread_messages": _process_unread_messages,
    # 仕入れ管理
    "record_procurement": _record_procurement,
    "update_procurement": _update_procurement,
    # Instagram
    "generate_instagram_post": _generate_instagram_post,
    "publish_instagram_post": _publish_instagram_post,
    "get_instagram_analytics": _get_instagram_analytics,
    "generate_dm_reply": _generate_dm_reply_handler,
    # 出品作成（バッチ対応）
    "get_category_aspects": _get_category_aspects_handler,
    "read_listing_sheet": _read_listing_sheet,
    "create_draft_listing": _create_draft_listing,
    "batch_create_drafts": _batch_create_drafts,
    "publish_draft_listings": _publish_draft_listings,
    # 利益管理
    "profit_summary": _profit_summary,
    "export_tax_report": _export_tax_report,
    # カテゴリ自動拡張
    "expand_categories": _expand_categories,
    # Shopify連携
    "sync_all_to_shopify": _sync_all_to_shopify,
    "set_shopify_discount": _set_shopify_discount,
    "get_shopify_status": _get_shopify_status,
    "remove_from_shopify": _remove_from_shopify,
}
