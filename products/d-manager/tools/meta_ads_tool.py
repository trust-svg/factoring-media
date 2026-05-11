"""Meta (Facebook) Ads tool — Discord向けMeta広告管理ツール.

facebook_business ライブラリを使用して Meta Marketing API と連携。
環境変数: META_ACCESS_TOKEN, META_AD_ACCOUNT_ID
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))

# Lazy-loaded API objects
_account = None
_initialized = False


def _ensure_api():
    """Lazy-init Facebook Marketing API."""
    global _account, _initialized
    if _initialized:
        return
    _initialized = True

    from facebook_business.api import FacebookAdsApi
    from facebook_business.adobjects.adaccount import AdAccount

    token = os.getenv("META_ACCESS_TOKEN")
    account_id = os.getenv("META_AD_ACCOUNT_ID")
    if not token or not account_id:
        raise RuntimeError("META_ACCESS_TOKEN / META_AD_ACCOUNT_ID が未設定です")

    FacebookAdsApi.init(access_token=token)
    _account = AdAccount(account_id)


def _fmt_number(n: float) -> str:
    """Format number with comma separator."""
    if n == int(n):
        return f"{int(n):,}"
    return f"{n:,.2f}"


# ---------------------------------------------------------------------------
# 1. Weekly Report
# ---------------------------------------------------------------------------

def meta_ads_weekly_report() -> str:
    """直近7日間のMeta広告パフォーマンスサマリーを取得"""
    try:
        _ensure_api()
        from facebook_business.adobjects.adaccount import AdAccount

        now = datetime.now(JST)
        since = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        until = now.strftime("%Y-%m-%d")

        params = {
            "time_range": {"since": since, "until": until},
            "level": "campaign",
        }
        fields = [
            "campaign_name", "impressions", "clicks", "ctr",
            "spend", "cpc", "actions", "cost_per_action_type",
        ]
        insights = list(_account.get_insights(fields=fields, params=params))

        if not insights:
            return "📊 **Meta広告 週次レポート**\n━━━━━━━━━━━━━━━\n該当期間のデータがありません。"

        total_spend = 0
        total_imp = 0
        total_clicks = 0
        total_conv = 0
        campaign_rows = []

        for row in insights:
            spend = float(row.get("spend", 0))
            imp = int(row.get("impressions", 0))
            clicks = int(row.get("clicks", 0))
            ctr = float(row.get("ctr", 0))
            cpc = float(row.get("cpc", 0))

            # Extract conversions
            actions = row.get("actions") or []
            conv = 0
            for a in actions:
                if a["action_type"] in (
                    "offsite_conversion.fb_pixel_complete_registration",
                    "complete_registration",
                    "offsite_conversion.fb_pixel_lead",
                    "lead",
                ):
                    conv += int(a.get("value", 0))

            # CPA from cost_per_action_type
            cost_per = row.get("cost_per_action_type") or []
            cpa = 0
            for c in cost_per:
                if c["action_type"] in (
                    "offsite_conversion.fb_pixel_complete_registration",
                    "complete_registration",
                    "offsite_conversion.fb_pixel_lead",
                    "lead",
                ):
                    cpa = float(c.get("value", 0))
                    break

            total_spend += spend
            total_imp += imp
            total_clicks += clicks
            total_conv += conv

            campaign_rows.append({
                "name": row.get("campaign_name", "不明"),
                "spend": spend,
                "imp": imp,
                "clicks": clicks,
                "ctr": ctr,
                "cpc": cpc,
                "conv": conv,
                "cpa": cpa,
            })

        avg_ctr = (total_clicks / total_imp * 100) if total_imp > 0 else 0
        avg_cpa = (total_spend / total_conv) if total_conv > 0 else 0
        roas_note = "※ ROAS算出には売上データ連携が必要"

        lines = [
            f"📊 **Meta広告 週次レポート**（{since} 〜 {until}）",
            "━━━━━━━━━━━━━━━",
            f"💰 総消化: **¥{_fmt_number(total_spend)}**",
            f"👁 インプレッション: **{_fmt_number(total_imp)}**",
            f"👆 クリック: **{_fmt_number(total_clicks)}**（CTR **{avg_ctr:.2f}%**）",
            f"🎯 コンバージョン: **{total_conv}件**",
            f"📉 平均CPA: **¥{_fmt_number(avg_cpa)}**",
            f"📈 {roas_note}",
            "",
            "**キャンペーン別:**",
        ]
        for r in sorted(campaign_rows, key=lambda x: x["spend"], reverse=True):
            cpa_str = f"¥{_fmt_number(r['cpa'])}" if r["cpa"] > 0 else "-"
            lines.append(
                f"  • {r['name']}: ¥{_fmt_number(r['spend'])} / "
                f"{r['clicks']}click / {r['conv']}CV / CPA {cpa_str}"
            )
        lines.append("━━━━━━━━━━━━━━━")
        return "\n".join(lines)

    except Exception as e:
        logger.error(f"meta_ads_weekly_report error: {e}")
        return f"⚠️ Meta広告レポート取得エラー: {e}"


# ---------------------------------------------------------------------------
# 2. Campaign Status
# ---------------------------------------------------------------------------

def meta_ads_campaign_status() -> str:
    """全キャンペーンのステータス・予算・直近パフォーマンスを表示"""
    try:
        _ensure_api()
        from facebook_business.adobjects.campaign import Campaign

        fields = [
            Campaign.Field.name,
            Campaign.Field.status,
            Campaign.Field.daily_budget,
            Campaign.Field.lifetime_budget,
            Campaign.Field.effective_status,
        ]
        campaigns = list(_account.get_campaigns(fields=fields))

        if not campaigns:
            return "📋 キャンペーンが見つかりません。"

        # Get last 3 days insights per campaign
        now = datetime.now(JST)
        since = (now - timedelta(days=3)).strftime("%Y-%m-%d")
        until = now.strftime("%Y-%m-%d")
        insight_params = {
            "time_range": {"since": since, "until": until},
            "level": "campaign",
        }
        insight_fields = ["campaign_id", "campaign_name", "spend", "clicks", "impressions"]
        insights = list(_account.get_insights(fields=insight_fields, params=insight_params))
        perf_map = {}
        for row in insights:
            perf_map[row.get("campaign_id")] = {
                "spend": float(row.get("spend", 0)),
                "clicks": int(row.get("clicks", 0)),
                "imp": int(row.get("impressions", 0)),
            }

        status_icons = {
            "ACTIVE": "🟢",
            "PAUSED": "🔴",
            "DELETED": "⚫",
            "ARCHIVED": "⚫",
        }

        lines = [
            "📋 **Meta広告 キャンペーン一覧**",
            "━━━━━━━━━━━━━━━",
        ]
        for c in campaigns:
            eff_status = c.get("effective_status", "UNKNOWN")
            icon = status_icons.get(eff_status, "🟡")
            name = c.get("name", "不明")
            daily = c.get("daily_budget")
            budget_str = f"日予算¥{_fmt_number(int(daily)/100)}" if daily else "予算未設定"

            perf = perf_map.get(c.get("id"), {})
            perf_str = ""
            if perf:
                perf_str = f" | 直近3日: ¥{_fmt_number(perf['spend'])} / {perf['clicks']}click"

            lines.append(f"{icon} **{name}** [{eff_status}] {budget_str}{perf_str}")

        lines.append("━━━━━━━━━━━━━━━")
        return "\n".join(lines)

    except Exception as e:
        logger.error(f"meta_ads_campaign_status error: {e}")
        return f"⚠️ キャンペーン一覧取得エラー: {e}"


# ---------------------------------------------------------------------------
# 3. Pause Campaign
# ---------------------------------------------------------------------------

def meta_ads_pause_campaign(campaign_name: str) -> str:
    """キャンペーン名（部分一致）で一時停止する"""
    try:
        _ensure_api()
        from facebook_business.adobjects.campaign import Campaign

        fields = [Campaign.Field.name, Campaign.Field.status, Campaign.Field.effective_status]
        campaigns = list(_account.get_campaigns(fields=fields))

        matched = [
            c for c in campaigns
            if campaign_name.lower() in c.get("name", "").lower()
            and c.get("effective_status") == "ACTIVE"
        ]

        if not matched:
            return f"⚠️ アクティブなキャンペーン「{campaign_name}」が見つかりません。"

        if len(matched) > 1:
            names = ", ".join(c["name"] for c in matched)
            return f"⚠️ 複数のキャンペーンがマッチしました: {names}\nもう少し具体的な名前を指定してください。"

        target = matched[0]
        target.api_update(params={Campaign.Field.status: Campaign.Status.paused})
        return f"⏸ キャンペーン「**{target['name']}**」を一時停止しました。"

    except Exception as e:
        logger.error(f"meta_ads_pause_campaign error: {e}")
        return f"⚠️ キャンペーン停止エラー: {e}"


# ---------------------------------------------------------------------------
# 4. Resume Campaign
# ---------------------------------------------------------------------------

def meta_ads_resume_campaign(campaign_name: str) -> str:
    """キャンペーン名（部分一致）を再開する"""
    try:
        _ensure_api()
        from facebook_business.adobjects.campaign import Campaign

        fields = [Campaign.Field.name, Campaign.Field.status, Campaign.Field.effective_status]
        campaigns = list(_account.get_campaigns(fields=fields))

        matched = [
            c for c in campaigns
            if campaign_name.lower() in c.get("name", "").lower()
            and c.get("effective_status") == "PAUSED"
        ]

        if not matched:
            return f"⚠️ 一時停止中のキャンペーン「{campaign_name}」が見つかりません。"

        if len(matched) > 1:
            names = ", ".join(c["name"] for c in matched)
            return f"⚠️ 複数のキャンペーンがマッチしました: {names}\nもう少し具体的な名前を指定してください。"

        target = matched[0]
        target.api_update(params={Campaign.Field.status: Campaign.Status.active})
        return f"▶️ キャンペーン「**{target['name']}**」を再開しました。"

    except Exception as e:
        logger.error(f"meta_ads_resume_campaign error: {e}")
        return f"⚠️ キャンペーン再開エラー: {e}"


# ---------------------------------------------------------------------------
# 5. Set Budget
# ---------------------------------------------------------------------------

def meta_ads_set_budget(campaign_name: str, daily_budget: int) -> str:
    """キャンペーンの日予算を変更する（JPY）"""
    try:
        _ensure_api()
        from facebook_business.adobjects.campaign import Campaign

        if daily_budget < 100:
            return "⚠️ 日予算は100円以上を指定してください。"

        fields = [Campaign.Field.name, Campaign.Field.status, Campaign.Field.daily_budget]
        campaigns = list(_account.get_campaigns(fields=fields))

        matched = [
            c for c in campaigns
            if campaign_name.lower() in c.get("name", "").lower()
            and c.get("effective_status") not in ("DELETED", "ARCHIVED")
        ]

        if not matched:
            return f"⚠️ キャンペーン「{campaign_name}」が見つかりません。"

        if len(matched) > 1:
            names = ", ".join(c["name"] for c in matched)
            return f"⚠️ 複数のキャンペーンがマッチしました: {names}\nもう少し具体的な名前を指定してください。"

        target = matched[0]
        old_budget = target.get("daily_budget")
        old_str = f"¥{_fmt_number(int(old_budget)/100)}" if old_budget else "未設定"

        # Meta API expects budget in cents (smallest currency unit)
        target.api_update(params={Campaign.Field.daily_budget: daily_budget * 100})
        return (
            f"💰 キャンペーン「**{target['name']}**」の日予算を変更しました。\n"
            f"  変更前: {old_str} → 変更後: **¥{_fmt_number(daily_budget)}**"
        )

    except Exception as e:
        logger.error(f"meta_ads_set_budget error: {e}")
        return f"⚠️ 予算変更エラー: {e}"


# ---------------------------------------------------------------------------
# 6. Creative Fatigue Check
# ---------------------------------------------------------------------------

def meta_ads_creative_fatigue() -> str:
    """アクティブキャンペーンのフリークエンシーとCTR低下をチェック"""
    try:
        _ensure_api()

        now = datetime.now(JST)
        # Compare last 3 days vs previous 4 days
        recent_since = (now - timedelta(days=3)).strftime("%Y-%m-%d")
        recent_until = now.strftime("%Y-%m-%d")
        prev_since = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        prev_until = (now - timedelta(days=4)).strftime("%Y-%m-%d")

        fields = [
            "campaign_name", "impressions", "clicks", "ctr",
            "frequency", "spend",
        ]

        # Recent period
        recent_insights = list(_account.get_insights(
            fields=fields,
            params={
                "time_range": {"since": recent_since, "until": recent_until},
                "level": "campaign",
                "filtering": [{"field": "campaign.effective_status",
                               "operator": "IN", "value": ["ACTIVE"]}],
            },
        ))

        # Previous period
        prev_insights = list(_account.get_insights(
            fields=fields,
            params={
                "time_range": {"since": prev_since, "until": prev_until},
                "level": "campaign",
                "filtering": [{"field": "campaign.effective_status",
                               "operator": "IN", "value": ["ACTIVE"]}],
            },
        ))

        if not recent_insights:
            return "🔍 **クリエイティブ疲弊チェック**\n━━━━━━━━━━━━━━━\nアクティブキャンペーンのデータがありません。"

        prev_map = {}
        for row in prev_insights:
            prev_map[row.get("campaign_name")] = {
                "ctr": float(row.get("ctr", 0)),
                "freq": float(row.get("frequency", 0)),
            }

        alerts = []
        ok_campaigns = []

        for row in recent_insights:
            name = row.get("campaign_name", "不明")
            freq = float(row.get("frequency", 0))
            ctr = float(row.get("ctr", 0))
            imp = int(row.get("impressions", 0))

            prev = prev_map.get(name)
            ctr_change = ""
            if prev and prev["ctr"] > 0:
                change_pct = ((ctr - prev["ctr"]) / prev["ctr"]) * 100
                ctr_change = f"（前期比 {change_pct:+.1f}%）"

            issues = []
            if freq >= 3.0:
                issues.append(f"フリークエンシー **{freq:.1f}** → 疲弊リスク高")
            elif freq >= 2.0:
                issues.append(f"フリークエンシー **{freq:.1f}** → 要注意")

            if prev and prev["ctr"] > 0:
                change_pct = ((ctr - prev["ctr"]) / prev["ctr"]) * 100
                if change_pct <= -20:
                    issues.append(f"CTR **{ctr:.2f}%** {ctr_change} → 大幅低下")
                elif change_pct <= -10:
                    issues.append(f"CTR **{ctr:.2f}%** {ctr_change} → やや低下")

            if issues:
                alerts.append(f"🔴 **{name}**\n" + "\n".join(f"  • {i}" for i in issues))
            else:
                ok_campaigns.append(f"🟢 {name}: freq {freq:.1f} / CTR {ctr:.2f}%{ctr_change}")

        lines = [
            "🔍 **クリエイティブ疲弊チェック**",
            f"━━━━━━━━━━━━━━━ 分析期間: {prev_since} 〜 {recent_until}",
        ]

        if alerts:
            lines.append("\n**⚠️ 疲弊アラート:**")
            lines.extend(alerts)
            lines.append("\n💡 対策: クリエイティブ差替え / オーディエンス拡張 / 広告セット再作成")
        else:
            lines.append("\n✅ 疲弊兆候のあるキャンペーンはありません。")

        if ok_campaigns:
            lines.append("\n**正常なキャンペーン:**")
            lines.extend(ok_campaigns)

        lines.append("━━━━━━━━━━━━━━━")
        return "\n".join(lines)

    except Exception as e:
        logger.error(f"meta_ads_creative_fatigue error: {e}")
        return f"⚠️ クリエイティブ疲弊チェックエラー: {e}"
