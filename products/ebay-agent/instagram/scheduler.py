"""Instagram 定期タスク — コンテンツ自動生成・分析同期"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from database.models import get_db, InstagramPost
from database import crud
from instagram.client import InstagramClient

logger = logging.getLogger(__name__)


def auto_generate_instagram_content():
    """新規出品からInstagram投稿ドラフトを自動生成（毎日10:00 JST）

    前日以降に取得された出品で、まだInstagram投稿が生成されていないものを対象に
    自動でドラフトを生成する。
    """
    import asyncio
    from instagram.content_generator import generate_instagram_content

    db = get_db()
    try:
        cutoff = datetime.utcnow() - timedelta(days=1)

        # 最近取得された出品を取得
        from database.models import Listing
        recent_listings = (
            db.query(Listing)
            .filter(Listing.fetched_at >= cutoff, Listing.quantity > 0)
            .all()
        )

        # 既にInstagram投稿が作られているSKUを除外
        existing_skus = set(
            row[0] for row in
            db.query(InstagramPost.sku)
            .filter(InstagramPost.created_at >= cutoff)
            .all()
        )

        new_listings = [l for l in recent_listings if l.sku not in existing_skus]

        if not new_listings:
            logger.info("Instagram自動生成: 新規対象なし")
            return

        logger.info(f"Instagram自動生成: {len(new_listings)}件の新規出品を処理")

        # 高額商品を優先（上位5件まで）
        new_listings.sort(key=lambda l: l.price_usd, reverse=True)
        targets = new_listings[:5]

        results = []
        for listing in targets:
            try:
                result = asyncio.get_event_loop().run_until_complete(
                    generate_instagram_content(
                        sku=listing.sku,
                        content_type="carousel",
                        tone="showcase",
                    )
                )
                results.append(result)
                logger.info(f"  生成完了: {listing.sku} ({listing.title[:30]})")
            except Exception as e:
                logger.warning(f"  生成失敗: {listing.sku} — {e}")

        logger.info(f"Instagram自動生成完了: {len(results)}/{len(targets)}件成功")
    finally:
        db.close()


def sync_instagram_analytics():
    """Instagram投稿のパフォーマンスデータを同期（毎日23:00 JST）"""
    client = InstagramClient()
    if not client.is_connected:
        logger.info("Instagram分析同期: APIモック — スキップ")
        return

    db = get_db()
    try:
        cutoff = datetime.utcnow() - timedelta(days=30)
        posts = (
            db.query(InstagramPost)
            .filter(
                InstagramPost.status == "published",
                InstagramPost.published_at >= cutoff,
                InstagramPost.ig_post_id != "",
            )
            .all()
        )

        if not posts:
            logger.info("Instagram分析同期: 公開済み投稿なし")
            return

        updated = 0
        for post in posts:
            try:
                insights = client.get_media_insights(post.ig_post_id)
                post.impressions = insights.get("impressions", post.impressions)
                post.reach = insights.get("reach", post.reach)
                post.saves = insights.get("saved", post.saves)
                updated += 1
            except Exception as e:
                logger.warning(f"  分析取得失敗: {post.ig_post_id} — {e}")

        db.commit()
        logger.info(f"Instagram分析同期完了: {updated}/{len(posts)}件更新")
    finally:
        db.close()
