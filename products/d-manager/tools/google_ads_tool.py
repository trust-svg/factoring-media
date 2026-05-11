"""Google Ads ツール — d-manager Discord Bot 用.

Google Ads API を直接呼び出し、フォーマット済み文字列を返す。
"""

import logging
import os
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)
JST = timezone(timedelta(hours=9))

# ---------------------------------------------------------------------------
# 設定
# ---------------------------------------------------------------------------

DEVELOPER_TOKEN = os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN", "")
CLIENT_ID = os.getenv("GOOGLE_ADS_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("GOOGLE_ADS_CLIENT_SECRET", "")
REFRESH_TOKEN = os.getenv("GOOGLE_ADS_REFRESH_TOKEN", "")
CUSTOMER_ID = os.getenv("GOOGLE_ADS_CUSTOMER_ID", "5225110150")
LOGIN_CUSTOMER_ID = os.getenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID", "1099749992")


def _get_client():
    """Google Ads API クライアントを生成."""
    from google.ads.googleads.client import GoogleAdsClient

    config = {
        "developer_token": DEVELOPER_TOKEN,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN,
        "login_customer_id": LOGIN_CUSTOMER_ID,
        "use_proto_plus": True,
    }
    return GoogleAdsClient.load_from_dict(config)


def _date_range(days: int = 7) -> tuple[str, str]:
    """過去 N 日の期間を (since, until) で返す."""
    today = datetime.now(JST).date()
    until = today - timedelta(days=1)
    since = until - timedelta(days=days - 1)
    return since.isoformat(), until.isoformat()


# ---------------------------------------------------------------------------
# コンバージョンアクション一覧
# ---------------------------------------------------------------------------

def google_ads_list_conversions() -> str:
    """コンバージョンアクション一覧を取得."""
    try:
        client = _get_client()
        service = client.get_service("GoogleAdsService")

        query = """
            SELECT
                conversion_action.name,
                conversion_action.status,
                conversion_action.type,
                conversion_action.category
            FROM conversion_action
            ORDER BY conversion_action.name
        """

        rows = []
        response = service.search_stream(customer_id=CUSTOMER_ID, query=query)
        for batch in response:
            for row in batch.results:
                status = str(row.conversion_action.status).split(".")[-1]
                ca_type = str(row.conversion_action.type).split(".")[-1]
                category = str(row.conversion_action.category).split(".")[-1]
                rows.append(
                    f"  • {row.conversion_action.name}  "
                    f"[{status}] タイプ: {ca_type} / カテゴリ: {category}"
                )

        if not rows:
            return "📊 コンバージョンアクションが見つかりませんでした。"

        return f"📊 **コンバージョンアクション一覧** ({len(rows)}件)\n" + "\n".join(rows)

    except Exception as e:
        logger.exception("google_ads_list_conversions エラー")
        return f"⚠️ コンバージョン一覧の取得に失敗しました: {e}"


# ---------------------------------------------------------------------------
# 除外キーワード追加
# ---------------------------------------------------------------------------

def google_ads_add_negative_kw(keywords: list[str]) -> str:
    """アクティブキャンペーンに除外キーワードを追加."""
    try:
        client = _get_client()
        service = client.get_service("GoogleAdsService")
        campaign_service = client.get_service("CampaignCriterionService")

        # アクティブキャンペーンを取得
        query = "SELECT campaign.resource_name FROM campaign WHERE campaign.status = 'ENABLED'"
        campaigns = []
        response = service.search_stream(customer_id=CUSTOMER_ID, query=query)
        for batch in response:
            for row in batch.results:
                campaigns.append(row.campaign.resource_name)

        if not campaigns:
            return "⚠️ 有効なキャンペーンが見つかりません。"

        operations = []
        for campaign_rn in campaigns:
            for kw in keywords:
                op = client.get_type("CampaignCriterionOperation")
                criterion = op.create
                criterion.campaign = campaign_rn
                criterion.negative = True
                criterion.keyword.text = kw
                criterion.keyword.match_type = client.enums.KeywordMatchTypeEnum.EXACT
                operations.append(op)

        resp = campaign_service.mutate_campaign_criteria(
            customer_id=CUSTOMER_ID, operations=operations
        )

        added = len(resp.results)
        kw_list = ", ".join(keywords)
        return (
            f"🚫 **除外キーワード追加完了**\n"
            f"  キーワード: {kw_list}\n"
            f"  対象キャンペーン: {len(campaigns)}件\n"
            f"  追加数: {added}件"
        )

    except Exception as e:
        logger.exception("google_ads_add_negative_kw エラー")
        return f"⚠️ 除外キーワードの追加に失敗しました: {e}"


# ---------------------------------------------------------------------------
# 除外キーワード削除
# ---------------------------------------------------------------------------

def google_ads_remove_negative_kw(keywords: list[str]) -> str:
    """アクティブキャンペーンから除外キーワードを削除."""
    try:
        client = _get_client()
        service = client.get_service("GoogleAdsService")
        campaign_service = client.get_service("CampaignCriterionService")

        kw_set = {kw.lower() for kw in keywords}

        query = """
            SELECT
                campaign_criterion.resource_name,
                campaign_criterion.keyword.text,
                campaign_criterion.negative
            FROM campaign_criterion
            WHERE campaign_criterion.negative = TRUE
                AND campaign_criterion.type = 'KEYWORD'
                AND campaign.status = 'ENABLED'
        """

        to_remove = []
        response = service.search_stream(customer_id=CUSTOMER_ID, query=query)
        for batch in response:
            for row in batch.results:
                if row.campaign_criterion.keyword.text.lower() in kw_set:
                    to_remove.append(row.campaign_criterion.resource_name)

        if not to_remove:
            return f"⚠️ 該当する除外キーワードが見つかりません: {', '.join(keywords)}"

        operations = []
        for rn in to_remove:
            op = client.get_type("CampaignCriterionOperation")
            op.remove = rn
            operations.append(op)

        resp = campaign_service.mutate_campaign_criteria(
            customer_id=CUSTOMER_ID, operations=operations
        )

        return (
            f"✅ **除外キーワード削除完了**\n"
            f"  キーワード: {', '.join(keywords)}\n"
            f"  削除数: {len(resp.results)}件"
        )

    except Exception as e:
        logger.exception("google_ads_remove_negative_kw エラー")
        return f"⚠️ 除外キーワードの削除に失敗しました: {e}"


# ---------------------------------------------------------------------------
# キーワード追加
# ---------------------------------------------------------------------------

def google_ads_add_kw(keywords: list[str], match_type: str = "exact") -> str:
    """アクティブキャンペーンの広告グループにキーワードを追加."""
    try:
        client = _get_client()
        service = client.get_service("GoogleAdsService")
        ag_service = client.get_service("AdGroupCriterionService")

        match_map = {
            "exact": client.enums.KeywordMatchTypeEnum.EXACT,
            "phrase": client.enums.KeywordMatchTypeEnum.PHRASE,
            "broad": client.enums.KeywordMatchTypeEnum.BROAD,
        }
        mt = match_map.get(match_type.lower(), client.enums.KeywordMatchTypeEnum.EXACT)
        mt_label = {"exact": "完全一致", "phrase": "フレーズ一致", "broad": "インテント マッチ"}.get(
            match_type.lower(), match_type
        )

        # アクティブな広告グループを取得
        query = """
            SELECT ad_group.resource_name, ad_group.name
            FROM ad_group
            WHERE campaign.status = 'ENABLED'
                AND ad_group.status = 'ENABLED'
        """

        ad_groups = []
        response = service.search_stream(customer_id=CUSTOMER_ID, query=query)
        for batch in response:
            for row in batch.results:
                ad_groups.append((row.ad_group.resource_name, row.ad_group.name))

        if not ad_groups:
            return "⚠️ 有効な広告グループが見つかりません。"

        operations = []
        for ag_rn, _ag_name in ad_groups:
            for kw in keywords:
                op = client.get_type("AdGroupCriterionOperation")
                criterion = op.create
                criterion.ad_group = ag_rn
                criterion.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
                criterion.keyword.text = kw
                criterion.keyword.match_type = mt
                operations.append(op)

        resp = ag_service.mutate_ad_group_criteria(
            customer_id=CUSTOMER_ID, operations=operations
        )

        kw_list = ", ".join(keywords)
        return (
            f"✅ **キーワード追加完了**\n"
            f"  キーワード: {kw_list}\n"
            f"  マッチタイプ: {mt_label}\n"
            f"  対象広告グループ: {len(ad_groups)}件\n"
            f"  追加数: {len(resp.results)}件"
        )

    except Exception as e:
        logger.exception("google_ads_add_kw エラー")
        return f"⚠️ キーワードの追加に失敗しました: {e}"


# ---------------------------------------------------------------------------
# 週次レポート
# ---------------------------------------------------------------------------

def google_ads_weekly_report() -> str:
    """直近7日間のキャンペーン＋キーワードサマリーを生成."""
    try:
        client = _get_client()
        service = client.get_service("GoogleAdsService")
        since, until = _date_range(7)

        # --- キャンペーンデータ ---
        c_query = f"""
            SELECT
                campaign.name,
                metrics.impressions, metrics.clicks, metrics.ctr,
                metrics.average_cpc, metrics.cost_micros,
                metrics.conversions, metrics.cost_per_conversion
            FROM campaign
            WHERE segments.date BETWEEN '{since}' AND '{until}'
                AND campaign.status = 'ENABLED'
        """

        total = {"imp": 0, "clicks": 0, "cost": 0, "conv": 0}
        camp_lines = []
        response = service.search_stream(customer_id=CUSTOMER_ID, query=c_query)
        for batch in response:
            for row in batch.results:
                cost = row.metrics.cost_micros / 1_000_000
                clicks = row.metrics.clicks
                conv = row.metrics.conversions
                cpa = (cost / conv) if conv > 0 else 0
                total["imp"] += row.metrics.impressions
                total["clicks"] += clicks
                total["cost"] += cost
                total["conv"] += conv
                camp_lines.append(
                    f"  • **{row.campaign.name}**\n"
                    f"    表示{row.metrics.impressions:,} / "
                    f"クリック{clicks:,} / "
                    f"費用¥{cost:,.0f} / "
                    f"CV{conv:.1f} / "
                    f"CPA¥{cpa:,.0f}"
                )

        # --- キーワード TOP5 (クリック順) ---
        k_query = f"""
            SELECT
                ad_group_criterion.keyword.text,
                ad_group_criterion.keyword.match_type,
                metrics.clicks, metrics.impressions,
                metrics.cost_micros, metrics.conversions
            FROM keyword_view
            WHERE segments.date BETWEEN '{since}' AND '{until}'
                AND campaign.status = 'ENABLED'
        """

        kw_data = []
        response = service.search_stream(customer_id=CUSTOMER_ID, query=k_query)
        for batch in response:
            for row in batch.results:
                kw_data.append({
                    "kw": row.ad_group_criterion.keyword.text,
                    "clicks": row.metrics.clicks,
                    "cost": row.metrics.cost_micros / 1_000_000,
                    "conv": row.metrics.conversions,
                })

        kw_data.sort(key=lambda x: x["clicks"], reverse=True)
        top_kw = kw_data[:5]
        kw_lines = []
        for i, k in enumerate(top_kw, 1):
            cpa = (k["cost"] / k["conv"]) if k["conv"] > 0 else 0
            kw_lines.append(
                f"  {i}. {k['kw']} — "
                f"クリック{k['clicks']:,} / ¥{k['cost']:,.0f} / CV{k['conv']:.1f}"
            )

        # --- サマリー組み立て ---
        t_cpa = (total["cost"] / total["conv"]) if total["conv"] > 0 else 0
        t_ctr = (total["clicks"] / total["imp"] * 100) if total["imp"] > 0 else 0
        t_cpc = (total["cost"] / total["clicks"]) if total["clicks"] > 0 else 0

        lines = [
            f"📊 **Google Ads 週次レポート** ({since} ~ {until})",
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"📈 **全体サマリー**",
            f"  表示: **{total['imp']:,}** / クリック: **{total['clicks']:,}** / CTR: **{t_ctr:.2f}%**",
            f"  費用: **¥{total['cost']:,.0f}** / CPC: **¥{t_cpc:,.0f}**",
            f"  CV: **{total['conv']:.1f}** / CPA: **¥{t_cpa:,.0f}**",
            "",
            "🎯 **キャンペーン別**",
        ]
        lines.extend(camp_lines or ["  データなし"])
        lines.append("")
        lines.append("🔑 **キーワード TOP5 (クリック順)**")
        lines.extend(kw_lines or ["  データなし"])
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")

        return "\n".join(lines)

    except Exception as e:
        logger.exception("google_ads_weekly_report エラー")
        return f"⚠️ 週次レポートの取得に失敗しました: {e}"


# ---------------------------------------------------------------------------
# 検索語句分析
# ---------------------------------------------------------------------------

def google_ads_search_terms(days: int = 7) -> str:
    """検索語句データを取得し、CV有無で分類して返す."""
    try:
        client = _get_client()
        service = client.get_service("GoogleAdsService")
        since, until = _date_range(days)

        query = f"""
            SELECT
                search_term_view.search_term,
                metrics.impressions, metrics.clicks,
                metrics.cost_micros, metrics.conversions
            FROM search_term_view
            WHERE segments.date BETWEEN '{since}' AND '{until}'
                AND campaign.status = 'ENABLED'
                AND metrics.impressions > 0
        """

        terms = []
        response = service.search_stream(customer_id=CUSTOMER_ID, query=query)
        for batch in response:
            for row in batch.results:
                terms.append({
                    "term": row.search_term_view.search_term,
                    "imp": row.metrics.impressions,
                    "clicks": row.metrics.clicks,
                    "cost": row.metrics.cost_micros / 1_000_000,
                    "conv": row.metrics.conversions,
                })

        if not terms:
            return f"📊 検索語句データなし ({since} ~ {until})"

        cv_terms = [t for t in terms if t["conv"] > 0]
        no_cv_terms = [t for t in terms if t["conv"] == 0 and t["clicks"] > 0]

        cv_terms.sort(key=lambda x: x["conv"], reverse=True)
        no_cv_terms.sort(key=lambda x: x["cost"], reverse=True)

        lines = [
            f"🔍 **検索語句分析** ({since} ~ {until})",
            f"  総検索語句数: **{len(terms)}件**",
            "",
            f"🟢 **CV獲得語句** ({len(cv_terms)}件)",
        ]

        for t in cv_terms[:10]:
            cpa = (t["cost"] / t["conv"]) if t["conv"] > 0 else 0
            lines.append(
                f"  • {t['term']} — CV{t['conv']:.1f} / "
                f"クリック{t['clicks']} / ¥{t['cost']:,.0f} / CPA¥{cpa:,.0f}"
            )

        lines.append("")
        lines.append(f"🔴 **費用消化・CV無し TOP10** ({len(no_cv_terms)}件中)")
        for t in no_cv_terms[:10]:
            lines.append(
                f"  • {t['term']} — クリック{t['clicks']} / ¥{t['cost']:,.0f}"
            )

        total_waste = sum(t["cost"] for t in no_cv_terms)
        lines.append(f"\n  💰 CV無し語句の総費用: **¥{total_waste:,.0f}**")

        return "\n".join(lines)

    except Exception as e:
        logger.exception("google_ads_search_terms エラー")
        return f"⚠️ 検索語句の取得に失敗しました: {e}"
