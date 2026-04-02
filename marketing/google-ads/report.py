"""
Google Ads パフォーマンスレポート
API からデータ取得 → 分析 → LINE通知
CSVフォールバック対応
"""

import os
import csv
import json
import datetime
import urllib.request
import urllib.error
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / "google-ads.env")

# Google Ads API
DEVELOPER_TOKEN = os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN")
CLIENT_ID = os.getenv("GOOGLE_ADS_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_ADS_CLIENT_SECRET")
REFRESH_TOKEN = os.getenv("GOOGLE_ADS_REFRESH_TOKEN")
CUSTOMER_ID = os.getenv("GOOGLE_ADS_CUSTOMER_ID")
LOGIN_CUSTOMER_ID = os.getenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID")

# LINE (legacy)
LINE_CHANNEL_TOKEN = os.getenv("LINE_CHANNEL_TOKEN")

# Discord
DISCORD_MARKETING_WEBHOOK = os.getenv("DISCORD_MARKETING_WEBHOOK")

REPORT_DIR = Path(__file__).parent / "report"
GDRIVE_REPORT_DIR = Path("/Users/Mac_air/Library/CloudStorage/GoogleDrive-otsuka@trustlink-tk.com/マイドライブ/広告関連/マッチング/Google広告/レポート")

# ベンチマーク（マッチングアプリ / 日本市場）
BENCH = {
    "ctr": 6.66,       # %
    "cpc": 310,         # 円
    "cvr": 7.52,        # %
    "cpa": 5000,        # 円（本登録ベース推定）
}


# ============================================================
# Google Ads API データ取得
# ============================================================

def get_google_ads_client():
    """Google Ads APIクライアントを初期化"""
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


def fetch_campaign_data(client, since, until):
    """キャンペーンデータをAPIから取得"""
    service = client.get_service("GoogleAdsService")

    query = f"""
        SELECT
            campaign.name,
            campaign.status,
            campaign.advertising_channel_type,
            metrics.impressions,
            metrics.clicks,
            metrics.ctr,
            metrics.average_cpc,
            metrics.cost_micros,
            metrics.conversions,
            metrics.conversions_value,
            metrics.cost_per_conversion,
            metrics.conversions_from_interactions_rate,
            metrics.search_impression_share,
            metrics.search_top_impression_share,
            metrics.search_absolute_top_impression_share,
            metrics.search_budget_lost_impression_share,
            metrics.search_rank_lost_impression_share
        FROM campaign
        WHERE segments.date BETWEEN '{since}' AND '{until}'
            AND campaign.status = 'ENABLED'
    """

    campaigns = []
    response = service.search_stream(customer_id=CUSTOMER_ID, query=query)
    for batch in response:
        for row in batch.results:
            cost = row.metrics.cost_micros / 1_000_000
            clicks = row.metrics.clicks
            imp = row.metrics.impressions
            conv = row.metrics.conversions
            campaigns.append({
                "name": row.campaign.name,
                "status": "有効",
                "type": str(row.campaign.advertising_channel_type).split(".")[-1],
                "clicks": clicks,
                "impressions": imp,
                "ctr": row.metrics.ctr * 100,
                "cpc": row.metrics.average_cpc / 1_000_000 if clicks > 0 else 0,
                "cost": cost,
                "top_is": (row.metrics.search_top_impression_share or 0) * 100,
                "abs_top_is": (row.metrics.search_absolute_top_impression_share or 0) * 100,
                "conversions": conv,
                "vt_conversions": 0,
                "cpa": (cost / conv) if conv > 0 else 0,
                "cvr": (conv / clicks * 100) if clicks > 0 else 0,
                "search_is": (row.metrics.search_impression_share or 0) * 100,
                "budget_lost_is": (row.metrics.search_budget_lost_impression_share or 0) * 100,
                "rank_lost_is": (row.metrics.search_rank_lost_impression_share or 0) * 100,
            })

    return campaigns


def fetch_keyword_data(client, since, until):
    """キーワードデータをAPIから取得"""
    service = client.get_service("GoogleAdsService")

    query = f"""
        SELECT
            ad_group_criterion.keyword.text,
            ad_group_criterion.keyword.match_type,
            ad_group_criterion.status,
            campaign.name,
            metrics.impressions,
            metrics.clicks,
            metrics.ctr,
            metrics.average_cpc,
            metrics.cost_micros,
            metrics.conversions,
            metrics.cost_per_conversion,
            metrics.conversions_from_interactions_rate,
            metrics.search_impression_share,
            metrics.search_top_impression_share
        FROM keyword_view
        WHERE segments.date BETWEEN '{since}' AND '{until}'
            AND campaign.status = 'ENABLED'
    """

    keywords = []
    response = service.search_stream(customer_id=CUSTOMER_ID, query=query)
    for batch in response:
        for row in batch.results:
            cost = row.metrics.cost_micros / 1_000_000
            clicks = row.metrics.clicks
            conv = row.metrics.conversions
            match_type = str(row.ad_group_criterion.keyword.match_type).split(".")[-1]
            match_label = {"EXACT": "完全一致", "PHRASE": "フレーズ一致", "BROAD": "インテント マッチ"}.get(match_type, match_type)

            keywords.append({
                "keyword": row.ad_group_criterion.keyword.text,
                "status": "有効" if str(row.ad_group_criterion.status).endswith("ENABLED") else "一時停止中",
                "match_type": match_label,
                "campaign": row.campaign.name,
                "clicks": clicks,
                "impressions": row.metrics.impressions,
                "ctr": row.metrics.ctr * 100,
                "cpc": row.metrics.average_cpc / 1_000_000 if clicks > 0 else 0,
                "cost": cost,
                "top_is": (row.metrics.search_top_impression_share or 0) * 100,
                "abs_top_is": 0,
                "conversions": conv,
                "cpa": (cost / conv) if conv > 0 else 0,
                "cvr": (conv / clicks * 100) if clicks > 0 else 0,
            })

    return keywords


def fetch_adgroup_data(client, since, until):
    """広告グループデータをAPIから取得"""
    service = client.get_service("GoogleAdsService")

    query = f"""
        SELECT
            ad_group.name,
            campaign.name,
            ad_group.status,
            metrics.impressions,
            metrics.clicks,
            metrics.ctr,
            metrics.average_cpc,
            metrics.cost_micros,
            metrics.conversions,
            metrics.cost_per_conversion,
            metrics.conversions_from_interactions_rate
        FROM ad_group
        WHERE segments.date BETWEEN '{since}' AND '{until}'
            AND campaign.status = 'ENABLED'
            AND ad_group.status = 'ENABLED'
    """

    adgroups = []
    response = service.search_stream(customer_id=CUSTOMER_ID, query=query)
    for batch in response:
        for row in batch.results:
            cost = row.metrics.cost_micros / 1_000_000
            clicks = row.metrics.clicks
            conv = row.metrics.conversions
            adgroups.append({
                "name": row.ad_group.name,
                "campaign": row.campaign.name,
                "bid_strategy": "",
                "active_ads": 0,
                "active_keywords": 0,
                "desktop_adj": "",
                "mobile_adj": "",
                "tablet_adj": "",
                "clicks": clicks,
                "impressions": row.metrics.impressions,
                "ctr": row.metrics.ctr * 100,
                "cpc": row.metrics.average_cpc / 1_000_000 if clicks > 0 else 0,
                "cost": cost,
                "conversions": conv,
                "cpa": (cost / conv) if conv > 0 else 0,
                "cvr": (conv / clicks * 100) if clicks > 0 else 0,
            })

    return adgroups


def fetch_search_terms(client, since, until):
    """検索語句データをAPIから取得"""
    service = client.get_service("GoogleAdsService")

    query = f"""
        SELECT
            search_term_view.search_term,
            search_term_view.status,
            metrics.impressions,
            metrics.clicks,
            metrics.ctr,
            metrics.cost_micros,
            metrics.conversions,
            metrics.conversions_from_interactions_rate
        FROM search_term_view
        WHERE segments.date BETWEEN '{since}' AND '{until}'
            AND campaign.status = 'ENABLED'
            AND metrics.impressions > 0
    """

    terms = []
    response = service.search_stream(customer_id=CUSTOMER_ID, query=query)
    for batch in response:
        for row in batch.results:
            cost = row.metrics.cost_micros / 1_000_000
            clicks = row.metrics.clicks
            conv = row.metrics.conversions
            status_str = str(row.search_term_view.status).split(".")[-1]
            terms.append({
                "search_term": row.search_term_view.search_term,
                "status": status_str,
                "impressions": row.metrics.impressions,
                "clicks": clicks,
                "ctr": row.metrics.ctr * 100,
                "cost": cost,
                "conversions": conv,
                "cvr": row.metrics.conversions_from_interactions_rate * 100,
            })

    return terms


def fetch_hourly_data(client, since, until):
    """曜日×時間帯データをAPIから取得"""
    service = client.get_service("GoogleAdsService")

    query = f"""
        SELECT
            segments.day_of_week,
            segments.hour,
            metrics.impressions,
            metrics.clicks,
            metrics.cost_micros,
            metrics.conversions
        FROM campaign
        WHERE segments.date BETWEEN '{since}' AND '{until}'
            AND campaign.status = 'ENABLED'
    """

    rows_out = []
    response = service.search_stream(customer_id=CUSTOMER_ID, query=query)
    for batch in response:
        for row in batch.results:
            day_str = str(row.segments.day_of_week).split(".")[-1]
            rows_out.append({
                "day_of_week": day_str,
                "hour": row.segments.hour,
                "impressions": row.metrics.impressions,
                "clicks": row.metrics.clicks,
                "cost": row.metrics.cost_micros / 1_000_000,
                "conversions": row.metrics.conversions,
            })

    return rows_out


def fetch_device_data(client, since, until):
    """デバイス別データをAPIから取得"""
    service = client.get_service("GoogleAdsService")

    query = f"""
        SELECT
            segments.device,
            metrics.impressions,
            metrics.clicks,
            metrics.ctr,
            metrics.cost_micros,
            metrics.conversions,
            metrics.conversions_from_interactions_rate
        FROM campaign
        WHERE segments.date BETWEEN '{since}' AND '{until}'
            AND campaign.status = 'ENABLED'
    """

    devices = []
    response = service.search_stream(customer_id=CUSTOMER_ID, query=query)
    for batch in response:
        for row in batch.results:
            cost = row.metrics.cost_micros / 1_000_000
            clicks = row.metrics.clicks
            conv = row.metrics.conversions
            device_str = str(row.segments.device).split(".")[-1]
            devices.append({
                "device": device_str,
                "impressions": row.metrics.impressions,
                "clicks": clicks,
                "ctr": row.metrics.ctr * 100,
                "cost": cost,
                "conversions": conv,
                "cvr": row.metrics.conversions_from_interactions_rate * 100,
            })

    # デバイスごとに集約
    agg = {}
    for d in devices:
        key = d["device"]
        if key not in agg:
            agg[key] = {"device": key, "impressions": 0, "clicks": 0, "cost": 0, "conversions": 0}
        agg[key]["impressions"] += d["impressions"]
        agg[key]["clicks"] += d["clicks"]
        agg[key]["cost"] += d["cost"]
        agg[key]["conversions"] += d["conversions"]

    result = []
    for key, a in agg.items():
        a["ctr"] = (a["clicks"] / a["impressions"] * 100) if a["impressions"] > 0 else 0
        a["cvr"] = (a["conversions"] / a["clicks"] * 100) if a["clicks"] > 0 else 0
        result.append(a)

    return result


def fetch_ad_data(client, since, until):
    """広告文別パフォーマンスをAPIから取得"""
    service = client.get_service("GoogleAdsService")

    query = f"""
        SELECT
            ad_group_ad.ad.responsive_search_ad.headlines,
            ad_group_ad.ad.final_urls,
            ad_group_ad.ad.id,
            ad_group.name,
            metrics.impressions,
            metrics.clicks,
            metrics.ctr,
            metrics.cost_micros,
            metrics.conversions,
            metrics.conversions_from_interactions_rate
        FROM ad_group_ad
        WHERE segments.date BETWEEN '{since}' AND '{until}'
            AND campaign.status = 'ENABLED'
            AND ad_group_ad.status = 'ENABLED'
    """

    ads = []
    response = service.search_stream(customer_id=CUSTOMER_ID, query=query)
    for batch in response:
        for row in batch.results:
            cost = row.metrics.cost_micros / 1_000_000
            clicks = row.metrics.clicks
            conv = row.metrics.conversions

            # 見出しを取得（最初の3つ）
            headlines_list = []
            try:
                for h in row.ad_group_ad.ad.responsive_search_ad.headlines[:3]:
                    headlines_list.append(h.text)
            except Exception:
                headlines_list = ["(見出し取得不可)"]
            headlines_str = " | ".join(headlines_list) if headlines_list else "(N/A)"

            ads.append({
                "ad_id": row.ad_group_ad.ad.id,
                "adgroup": row.ad_group.name,
                "headlines": headlines_str,
                "impressions": row.metrics.impressions,
                "clicks": clicks,
                "ctr": row.metrics.ctr * 100,
                "cost": cost,
                "conversions": conv,
                "cvr": row.metrics.conversions_from_interactions_rate * 100,
            })

    return ads


def fetch_geo_data(client, since, until):
    """地域別データをAPIから取得（複数クエリでフォールバック）"""
    service = client.get_service("GoogleAdsService")

    # 1st attempt: geographic_view (without geo_target_constant)
    try:
        query = f"""
            SELECT
                geographic_view.country_criterion_id,
                geographic_view.location_type,
                metrics.impressions,
                metrics.clicks,
                metrics.cost_micros,
                metrics.conversions
            FROM geographic_view
            WHERE segments.date BETWEEN '{since}' AND '{until}'
                AND campaign.status = 'ENABLED'
                AND metrics.impressions > 0
        """
        geo = []
        response = service.search_stream(customer_id=CUSTOMER_ID, query=query)
        for batch in response:
            for row in batch.results:
                geo.append({
                    "location": str(row.geographic_view.country_criterion_id),
                    "impressions": row.metrics.impressions,
                    "clicks": row.metrics.clicks,
                    "cost": row.metrics.cost_micros / 1_000_000,
                    "conversions": row.metrics.conversions,
                })
        return _aggregate_geo(geo)
    except Exception as e:
        print(f"  ⚠️ geographic_view失敗: {e}")

    # 2nd attempt: location_view
    try:
        query = f"""
            SELECT
                campaign_criterion.location.geo_target_constant,
                metrics.impressions,
                metrics.clicks,
                metrics.cost_micros,
                metrics.conversions
            FROM location_view
            WHERE segments.date BETWEEN '{since}' AND '{until}'
                AND campaign.status = 'ENABLED'
                AND metrics.impressions > 0
        """
        geo = []
        response = service.search_stream(customer_id=CUSTOMER_ID, query=query)
        for batch in response:
            for row in batch.results:
                geo.append({
                    "location": str(row.campaign_criterion.location.geo_target_constant),
                    "impressions": row.metrics.impressions,
                    "clicks": row.metrics.clicks,
                    "cost": row.metrics.cost_micros / 1_000_000,
                    "conversions": row.metrics.conversions,
                })
        return _aggregate_geo(geo)
    except Exception as e:
        print(f"  ⚠️ location_view失敗: {e}")

    # 3rd attempt: user_location_view
    try:
        query = f"""
            SELECT
                user_location_view.country_criterion_id,
                user_location_view.targeting_location,
                metrics.impressions,
                metrics.clicks,
                metrics.cost_micros,
                metrics.conversions
            FROM user_location_view
            WHERE segments.date BETWEEN '{since}' AND '{until}'
                AND campaign.status = 'ENABLED'
                AND metrics.impressions > 0
        """
        geo = []
        response = service.search_stream(customer_id=CUSTOMER_ID, query=query)
        for batch in response:
            for row in batch.results:
                geo.append({
                    "location": str(row.user_location_view.country_criterion_id),
                    "impressions": row.metrics.impressions,
                    "clicks": row.metrics.clicks,
                    "cost": row.metrics.cost_micros / 1_000_000,
                    "conversions": row.metrics.conversions,
                })
        return _aggregate_geo(geo)
    except Exception as e:
        print(f"  ⚠️ user_location_view失敗: {e}")

    return []


def _aggregate_geo(geo_list):
    """地域データを集約"""
    agg = {}
    for g in geo_list:
        key = g["location"]
        if key not in agg:
            agg[key] = {"location": key, "impressions": 0, "clicks": 0, "cost": 0, "conversions": 0}
        agg[key]["impressions"] += g["impressions"]
        agg[key]["clicks"] += g["clicks"]
        agg[key]["cost"] += g["cost"]
        agg[key]["conversions"] += g["conversions"]
    return list(agg.values())


# ============================================================
# Mutation（書き込み）操作
# ============================================================

def _confirm_action(description: str, dry_run: bool, confirm: bool) -> bool:
    """操作前の確認処理。dry_runならFalse、confirmフラグなしならy/nプロンプト"""
    print(f"\n📝 操作内容: {description}")
    if dry_run:
        print("  [DRY RUN] 実際の変更は行いません。")
        return False
    if confirm:
        return True
    answer = input("  実行しますか？ (y/n): ").strip().lower()
    return answer == "y"


def _get_active_campaign_id(client):
    """有効なキャンペーンのリソース名を取得（最初の1件）"""
    service = client.get_service("GoogleAdsService")
    query = """
        SELECT campaign.id, campaign.name, campaign.resource_name, campaign.status
        FROM campaign
        WHERE campaign.status = 'ENABLED'
        LIMIT 1
    """
    try:
        response = service.search_stream(customer_id=CUSTOMER_ID, query=query)
        for batch in response:
            for row in batch.results:
                return row.campaign.resource_name, row.campaign.name, row.campaign.id
    except Exception as e:
        print(f"⚠️  キャンペーン取得エラー: {e}")
        # ENABLED で見つからない場合、ステータスなしで再試行
        try:
            query2 = """
                SELECT campaign.id, campaign.name, campaign.resource_name, campaign.status
                FROM campaign
                LIMIT 5
            """
            response2 = service.search_stream(customer_id=CUSTOMER_ID, query=query2)
            campaigns = []
            for batch in response2:
                for row in batch.results:
                    status = str(row.campaign.status).split(".")[-1]
                    campaigns.append(f"  {row.campaign.name} [{status}] (ID: {row.campaign.id})")
            if campaigns:
                print("利用可能なキャンペーン:")
                for c in campaigns:
                    print(c)
            else:
                print("⚠️  アカウントにキャンペーンが存在しません。")
        except Exception as e2:
            print(f"⚠️  再試行エラー: {e2}")
    return None, None, None


def _get_active_adgroup_id(client):
    """有効な広告グループのリソース名を取得（最初の1件）"""
    service = client.get_service("GoogleAdsService")
    query = """
        SELECT ad_group.id, ad_group.name, ad_group.resource_name, campaign.name
        FROM ad_group
        WHERE campaign.status = 'ENABLED'
            AND ad_group.status = 'ENABLED'
        LIMIT 1
    """
    try:
        response = service.search_stream(customer_id=CUSTOMER_ID, query=query)
        for batch in response:
            for row in batch.results:
                return row.ad_group.resource_name, row.ad_group.name, row.campaign.name
    except Exception as e:
        print(f"⚠️  広告グループ取得エラー: {e}")
    return None, None, None


# --- 1. コンバージョンアクション一覧 ---

def list_conversion_actions(client):
    """全コンバージョンアクションを取得して表形式で表示"""
    service = client.get_service("GoogleAdsService")

    # Step 1: コンバージョンアクション一覧を取得
    query = """
        SELECT
            conversion_action.name,
            conversion_action.status,
            conversion_action.category,
            conversion_action.counting_type,
            conversion_action.resource_name,
            conversion_action.id,
            conversion_action.type
        FROM conversion_action
        ORDER BY conversion_action.name
    """

    actions = []
    try:
        response = service.search_stream(customer_id=CUSTOMER_ID, query=query)
        for batch in response:
            for row in batch.results:
                actions.append({
                    "name": row.conversion_action.name,
                    "status": str(row.conversion_action.status).split(".")[-1],
                    "category": str(row.conversion_action.category).split(".")[-1],
                    "counting": str(row.conversion_action.counting_type).split(".")[-1],
                    "type": str(row.conversion_action.type).split(".")[-1],
                    "resource_name": row.conversion_action.resource_name,
                    "id": row.conversion_action.id,
                })
    except Exception as e:
        print(f"❌ コンバージョンアクション取得エラー: {e}")
        return

    # Step 2: カスタマーコンバージョンゴールを取得（主要/副次の判定）
    primary_rns = set()
    try:
        goal_query = """
            SELECT
                customer_conversion_goal.category,
                customer_conversion_goal.origin,
                customer_conversion_goal.resource_name
            FROM customer_conversion_goal
        """
        response = service.search_stream(customer_id=CUSTOMER_ID, query=goal_query)
        for batch in response:
            for row in batch.results:
                primary_rns.add(row.customer_conversion_goal.resource_name)
    except Exception:
        pass  # ゴール取得できなくても一覧は表示する

    if not actions:
        print("コンバージョンアクションが見つかりません。")
        return

    # テーブル表示
    print(f"\n{'=' * 100}")
    print(f"コンバージョンアクション一覧 ({len(actions)}件)")
    print(f"{'=' * 100}")
    header = f"{'名前':<35} {'ステータス':<10} {'カテゴリ':<20} {'カウント':<12} {'タイプ':<15}"
    print(header)
    print("-" * 100)
    for a in actions:
        name_display = a['name'][:33] if len(a['name']) > 33 else a['name']
        print(f"{name_display:<35} {a['status']:<10} {a['category']:<20} {a['counting']:<12} {a['type']:<15}")
    print(f"{'=' * 100}")
    print(f"合計: {len(actions)}件 (有効: {sum(1 for a in actions if a['status'] == 'ENABLED')}件)\n")


# --- 2. コンバージョンアクションをセカンダリに変更 ---

def set_conversions_secondary(client, names: list[str], dry_run: bool = False, confirm: bool = False):
    """指定名（部分一致）のコンバージョンアクションをステータス変更

    Note: Google Ads APIでは「主要/副次」はcustomer_conversion_goalで管理される。
    ここではコンバージョンアクション自体のステータスを ENABLED/PAUSED に変更する。
    主要/副次の変更はGoogle Ads管理画面から行う必要がある。
    代替手段: コンバージョンアクションを PAUSED にすることで入札対象から外す。
    """
    service = client.get_service("GoogleAdsService")
    conv_service = client.get_service("ConversionActionService")

    # 全アクションを取得
    query = """
        SELECT
            conversion_action.name,
            conversion_action.resource_name,
            conversion_action.status,
            conversion_action.category
        FROM conversion_action
        WHERE conversion_action.status = 'ENABLED'
    """
    actions = []
    try:
        response = service.search_stream(customer_id=CUSTOMER_ID, query=query)
        for batch in response:
            for row in batch.results:
                actions.append({
                    "name": row.conversion_action.name,
                    "resource_name": row.conversion_action.resource_name,
                    "category": str(row.conversion_action.category).split(".")[-1],
                })
    except Exception as e:
        print(f"❌ コンバージョンアクション取得エラー: {e}")
        return

    # 部分一致でフィルタ
    matched = []
    seen = set()
    for name_pattern in names:
        for a in actions:
            if name_pattern in a["name"] and a["resource_name"] not in seen:
                matched.append(a)
                seen.add(a["resource_name"])

    if not matched:
        print(f"⚠️  一致するコンバージョンが見つかりません: {names}")
        if actions:
            print(f"利用可能なコンバージョン ({len(actions)}件):")
            for a in actions[:10]:
                print(f"    - {a['name']} [{a['category']}]")
        return

    desc = "以下のコンバージョンアクションを一時停止（PAUSED）に変更:\n" + \
           "\n".join(f"    - {a['name']} [{a['category']}]" for a in matched)
    print(f"\n⚠️  注意: APIではコンバージョンの「主要→副次」変更はできません。")
    print(f"代わりにステータスをPAUSEDにして入札対象から除外します。")
    print(f"主要/副次の変更はGoogle Ads管理画面 → 目標 → コンバージョンから行ってください。\n")

    if not _confirm_action(desc, dry_run, confirm):
        return

    # ミューテーション実行: ステータスを PAUSED に変更
    operations = []
    for a in matched:
        op = client.get_type("ConversionActionOperation")
        action = op.update
        action.resource_name = a["resource_name"]
        action.status = client.enums.ConversionActionStatusEnum.PAUSED
        client.copy_from(
            op.update_mask,
            client.get_type("FieldMask")(paths=["status"]),
        )
        operations.append(op)

    try:
        response = conv_service.mutate_conversion_actions(
            customer_id=CUSTOMER_ID,
            operations=operations,
        )
        print(f"✅ {len(response.results)}件のコンバージョンを一時停止しました。")
        for result in response.results:
            print(f"    {result.resource_name}")
    except Exception as e:
        print(f"❌ エラー: {e}")


# --- 3. 除外キーワード追加 ---

def add_negative_keywords(client, keywords: list[str], negative_list_name: str = None,
                          dry_run: bool = False, confirm: bool = False):
    """キャンペーンレベルの除外キーワードを追加（またはリスト経由）"""
    campaign_rn, campaign_name, campaign_id = _get_active_campaign_id(client)
    if not campaign_rn:
        print("⚠️  有効なキャンペーンが見つかりません。")
        return

    if negative_list_name:
        _add_negative_keywords_via_list(client, keywords, negative_list_name, campaign_rn,
                                        campaign_name, dry_run, confirm)
    else:
        _add_negative_keywords_to_campaign(client, keywords, campaign_rn, campaign_name,
                                           dry_run, confirm)


def _add_negative_keywords_to_campaign(client, keywords, campaign_rn, campaign_name,
                                        dry_run, confirm):
    """キャンペーンに直接除外キーワードを追加"""
    desc = f"キャンペーン「{campaign_name}」に除外キーワードを追加:\n" + \
           "\n".join(f"    - {kw}" for kw in keywords)
    if not _confirm_action(desc, dry_run, confirm):
        return

    campaign_criterion_service = client.get_service("CampaignCriterionService")
    operations = []
    for kw in keywords:
        op = client.get_type("CampaignCriterionOperation")
        criterion = op.create
        criterion.campaign = campaign_rn
        criterion.negative = True
        criterion.keyword.text = kw
        criterion.keyword.match_type = client.enums.KeywordMatchTypeEnum.PHRASE
        operations.append(op)

    try:
        response = campaign_criterion_service.mutate_campaign_criteria(
            customer_id=CUSTOMER_ID,
            operations=operations,
        )
        print(f"✅ {len(response.results)}件の除外キーワードを追加しました。")
        for result in response.results:
            print(f"    {result.resource_name}")
    except Exception as e:
        print(f"❌ エラー: {e}")


def _add_negative_keywords_via_list(client, keywords, list_name, campaign_rn, campaign_name,
                                     dry_run, confirm):
    """共有除外キーワードリスト経由で追加"""
    service = client.get_service("GoogleAdsService")
    skl_service = client.get_service("SharedSetService")
    shared_criterion_service = client.get_service("SharedCriterionService")
    campaign_shared_set_service = client.get_service("CampaignSharedSetService")

    # 既存リストを検索
    query = f"""
        SELECT shared_set.name, shared_set.resource_name, shared_set.id
        FROM shared_set
        WHERE shared_set.type = 'NEGATIVE_KEYWORDS'
            AND shared_set.status = 'ENABLED'
    """
    existing_list_rn = None
    response = service.search_stream(customer_id=CUSTOMER_ID, query=query)
    for batch in response:
        for row in batch.results:
            if row.shared_set.name == list_name:
                existing_list_rn = row.shared_set.resource_name
                break

    desc = f"除外リスト「{list_name}」にキーワードを追加 → キャンペーン「{campaign_name}」に適用:\n" + \
           "\n".join(f"    - {kw}" for kw in keywords)
    if existing_list_rn:
        desc += f"\n    (既存リスト使用: {existing_list_rn})"
    else:
        desc += "\n    (新規リスト作成)"
    if not _confirm_action(desc, dry_run, confirm):
        return

    # リストが無ければ作成
    if not existing_list_rn:
        op = client.get_type("SharedSetOperation")
        shared_set = op.create
        shared_set.name = list_name
        shared_set.type_ = client.enums.SharedSetTypeEnum.NEGATIVE_KEYWORDS
        try:
            resp = skl_service.mutate_shared_sets(
                customer_id=CUSTOMER_ID,
                operations=[op],
            )
            existing_list_rn = resp.results[0].resource_name
            print(f"  📁 除外リスト「{list_name}」を作成しました。")
        except Exception as e:
            print(f"❌ リスト作成エラー: {e}")
            return

    # リストにキーワード追加
    operations = []
    for kw in keywords:
        op = client.get_type("SharedCriterionOperation")
        criterion = op.create
        criterion.shared_set = existing_list_rn
        criterion.keyword.text = kw
        criterion.keyword.match_type = client.enums.KeywordMatchTypeEnum.PHRASE
        operations.append(op)

    try:
        resp = shared_criterion_service.mutate_shared_criteria(
            customer_id=CUSTOMER_ID,
            operations=operations,
        )
        print(f"  ✅ {len(resp.results)}件のキーワードをリストに追加しました。")
    except Exception as e:
        print(f"❌ リストへのキーワード追加エラー: {e}")
        return

    # リストをキャンペーンに関連付け（未関連付けの場合）
    query_linked = f"""
        SELECT campaign_shared_set.shared_set
        FROM campaign_shared_set
        WHERE campaign_shared_set.campaign = '{campaign_rn}'
            AND campaign_shared_set.shared_set = '{existing_list_rn}'
    """
    already_linked = False
    try:
        resp = service.search_stream(customer_id=CUSTOMER_ID, query=query_linked)
        for batch in resp:
            if batch.results:
                already_linked = True
                break
    except Exception:
        pass

    if not already_linked:
        op = client.get_type("CampaignSharedSetOperation")
        css = op.create
        css.campaign = campaign_rn
        css.shared_set = existing_list_rn
        try:
            campaign_shared_set_service.mutate_campaign_shared_sets(
                customer_id=CUSTOMER_ID,
                operations=[op],
            )
            print(f"  🔗 リストをキャンペーン「{campaign_name}」に関連付けました。")
        except Exception as e:
            print(f"❌ キャンペーン関連付けエラー: {e}")
    else:
        print(f"  ℹ️  リストは既にキャンペーンに関連付け済みです。")


# --- 3b. 除外キーワード削除 ---

def remove_negative_keywords(client, keywords: list[str], dry_run: bool = False, confirm: bool = False):
    """キャンペーンレベルの除外キーワードを削除"""
    campaign_rn, campaign_name, campaign_id = _get_active_campaign_id(client)
    if not campaign_rn:
        print("⚠️  有効なキャンペーンが見つかりません。")
        return

    service = client.get_service("GoogleAdsService")
    campaign_criterion_service = client.get_service("CampaignCriterionService")

    # 現在の除外KWを取得
    query = f"""
        SELECT
            campaign_criterion.criterion_id,
            campaign_criterion.keyword.text,
            campaign_criterion.keyword.match_type,
            campaign_criterion.resource_name
        FROM campaign_criterion
        WHERE campaign.resource_name = '{campaign_rn}'
            AND campaign_criterion.negative = TRUE
            AND campaign_criterion.type = 'KEYWORD'
    """
    existing = []
    try:
        response = service.search_stream(customer_id=CUSTOMER_ID, query=query)
        for batch in response:
            for row in batch.results:
                existing.append({
                    "text": row.campaign_criterion.keyword.text,
                    "resource_name": row.campaign_criterion.resource_name,
                })
    except Exception as e:
        print(f"❌ 除外KW取得エラー: {e}")
        return

    # 削除対象を特定（部分一致）
    to_remove = []
    for kw in keywords:
        for ex in existing:
            if kw.lower() == ex["text"].lower():
                to_remove.append(ex)
                break
        else:
            print(f"  ⚠️  除外KWに見つかりません: {kw}")

    if not to_remove:
        print("⚠️  削除対象の除外キーワードが見つかりません。")
        if existing:
            print(f"現在の除外KW ({len(existing)}件):")
            for ex in existing:
                print(f"    - {ex['text']}")
        return

    desc = f"キャンペーン「{campaign_name}」から除外キーワードを削除:\n" + \
           "\n".join(f"    - {r['text']}" for r in to_remove)
    if not _confirm_action(desc, dry_run, confirm):
        return

    operations = []
    for r in to_remove:
        op = client.get_type("CampaignCriterionOperation")
        op.remove = r["resource_name"]
        operations.append(op)

    try:
        response = campaign_criterion_service.mutate_campaign_criteria(
            customer_id=CUSTOMER_ID,
            operations=operations,
        )
        print(f"✅ {len(response.results)}件の除外キーワードを削除しました。")
        for result in response.results:
            print(f"    {result.resource_name}")
    except Exception as e:
        print(f"❌ エラー: {e}")


# --- 4. キーワード追加 ---

def add_keywords(client, keyword_texts: list[str], match_type: str = "exact",
                 dry_run: bool = False, confirm: bool = False):
    """広告グループにキーワードを追加"""
    adgroup_rn, adgroup_name, campaign_name = _get_active_adgroup_id(client)
    if not adgroup_rn:
        print("⚠️  有効な広告グループが見つかりません。")
        return

    match_map = {
        "exact": "EXACT",
        "phrase": "PHRASE",
        "broad": "BROAD",
    }
    match_enum_str = match_map.get(match_type.lower(), "EXACT")
    match_label = {"EXACT": "完全一致", "PHRASE": "フレーズ一致", "BROAD": "インテントマッチ"}.get(match_enum_str, match_enum_str)

    desc = f"広告グループ「{adgroup_name}」（{campaign_name}）にキーワードを追加:\n" + \
           "\n".join(f"    - [{match_label}] {kw}" for kw in keyword_texts)
    if not _confirm_action(desc, dry_run, confirm):
        return

    adgroup_criterion_service = client.get_service("AdGroupCriterionService")
    operations = []
    for kw in keyword_texts:
        op = client.get_type("AdGroupCriterionOperation")
        criterion = op.create
        criterion.ad_group = adgroup_rn
        criterion.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
        criterion.keyword.text = kw
        criterion.keyword.match_type = client.enums.KeywordMatchTypeEnum[match_enum_str]
        operations.append(op)

    try:
        response = adgroup_criterion_service.mutate_ad_group_criteria(
            customer_id=CUSTOMER_ID,
            operations=operations,
        )
        print(f"✅ {len(response.results)}件のキーワードを追加しました。")
        for result in response.results:
            print(f"    {result.resource_name}")
    except Exception as e:
        print(f"❌ エラー: {e}")


# --- 5. 入札戦略の設定 ---

def set_bidding_strategy(client, strategy: str, max_cpc: int = None, target_cpa: int = None,
                         dry_run: bool = False, confirm: bool = False):
    """キャンペーンの入札戦略を変更"""
    from google.api_core import protobuf_helpers

    campaign_rn, campaign_name, campaign_id = _get_active_campaign_id(client)
    if not campaign_rn:
        print("⚠️  有効なキャンペーンが見つかりません。")
        return

    strategy_lower = strategy.lower()
    desc_parts = [f"キャンペーン「{campaign_name}」の入札戦略を変更:"]
    desc_parts.append(f"    戦略: {strategy}")
    if max_cpc is not None:
        desc_parts.append(f"    上限CPC: ¥{max_cpc}")
    if target_cpa is not None:
        desc_parts.append(f"    目標CPA: ¥{target_cpa}")

    if not _confirm_action("\n".join(desc_parts), dry_run, confirm):
        return

    campaign_service = client.get_service("CampaignService")
    op = client.get_type("CampaignOperation")
    campaign = op.update
    campaign.resource_name = campaign_rn

    if strategy_lower == "maximize_conversions":
        campaign.maximize_conversions.CopyFrom(
            client.get_type("MaximizeConversions")()
        )
        if target_cpa is not None:
            campaign.maximize_conversions.target_cpa_micros = target_cpa * 1_000_000
    elif strategy_lower == "maximize_clicks":
        campaign.maximize_clicks.CopyFrom(
            client.get_type("MaximizeClicks")()
        )
        if max_cpc is not None:
            campaign.maximize_clicks.cpc_bid_ceiling_micros = max_cpc * 1_000_000
    elif strategy_lower == "target_cpa":
        campaign.maximize_conversions.CopyFrom(
            client.get_type("MaximizeConversions")()
        )
        if target_cpa is not None:
            campaign.maximize_conversions.target_cpa_micros = target_cpa * 1_000_000
        else:
            print("⚠️  target_cpa戦略には --target-cpa が必要です。")
            return
    elif strategy_lower == "manual_cpc":
        campaign.manual_cpc.CopyFrom(
            client.get_type("ManualCpc")()
        )
    else:
        print(f"⚠️  未対応の戦略: {strategy}")
        print("  対応: maximize_conversions, maximize_clicks, target_cpa, manual_cpc")
        return

    client.copy_from(
        op.update_mask,
        protobuf_helpers.field_mask(None, campaign._pb),
    )

    try:
        response = campaign_service.mutate_campaigns(
            customer_id=CUSTOMER_ID,
            operations=[op],
        )
        print(f"✅ 入札戦略を変更しました: {response.results[0].resource_name}")
    except Exception as e:
        print(f"❌ エラー: {e}")


# --- 6. 広告スケジュール入札調整 ---

def set_ad_schedule_bid_adjustments(client, schedule_json: str,
                                     dry_run: bool = False, confirm: bool = False):
    """曜日別入札調整を設定"""
    campaign_rn, campaign_name, campaign_id = _get_active_campaign_id(client)
    if not campaign_rn:
        print("⚠️  有効なキャンペーンが見つかりません。")
        return

    try:
        schedule = json.loads(schedule_json)
    except json.JSONDecodeError as e:
        print(f"⚠️  JSONパースエラー: {e}")
        return

    day_map = {
        "MONDAY": "MONDAY", "TUESDAY": "TUESDAY", "WEDNESDAY": "WEDNESDAY",
        "THURSDAY": "THURSDAY", "FRIDAY": "FRIDAY", "SATURDAY": "SATURDAY",
        "SUNDAY": "SUNDAY",
    }

    desc = f"キャンペーン「{campaign_name}」の曜日別入札調整:\n" + \
           "\n".join(f"    - {d}: {v:+d}%" for d, v in schedule.items())
    if not _confirm_action(desc, dry_run, confirm):
        return

    # 既存スケジュールを削除
    service = client.get_service("GoogleAdsService")
    campaign_criterion_service = client.get_service("CampaignCriterionService")

    query = f"""
        SELECT campaign_criterion.resource_name, campaign_criterion.criterion_id
        FROM campaign_criterion
        WHERE campaign_criterion.campaign = '{campaign_rn}'
            AND campaign_criterion.type = 'AD_SCHEDULE'
    """
    remove_ops = []
    try:
        response = service.search_stream(customer_id=CUSTOMER_ID, query=query)
        for batch in response:
            for row in batch.results:
                op = client.get_type("CampaignCriterionOperation")
                op.remove = row.campaign_criterion.resource_name
                remove_ops.append(op)
    except Exception:
        pass

    if remove_ops:
        try:
            campaign_criterion_service.mutate_campaign_criteria(
                customer_id=CUSTOMER_ID,
                operations=remove_ops,
            )
            print(f"  🗑️  既存スケジュール {len(remove_ops)}件を削除しました。")
        except Exception as e:
            print(f"  ⚠️ 既存スケジュール削除失敗: {e}")

    # 新規スケジュール作成（曜日ごとに終日、入札調整付き）
    create_ops = []
    for day_str, adj_percent in schedule.items():
        day_upper = day_str.upper()
        if day_upper not in day_map:
            print(f"  ⚠️ 不明な曜日: {day_str}")
            continue

        op = client.get_type("CampaignCriterionOperation")
        criterion = op.create
        criterion.campaign = campaign_rn
        criterion.bid_modifier = 1.0 + (adj_percent / 100.0)
        criterion.ad_schedule.day_of_week = client.enums.DayOfWeekEnum[day_upper]
        criterion.ad_schedule.start_hour = 0
        criterion.ad_schedule.start_minute = client.enums.MinuteOfHourEnum.ZERO
        criterion.ad_schedule.end_hour = 24
        criterion.ad_schedule.end_minute = client.enums.MinuteOfHourEnum.ZERO
        create_ops.append(op)

    if not create_ops:
        print("⚠️  設定するスケジュールがありません。")
        return

    try:
        response = campaign_criterion_service.mutate_campaign_criteria(
            customer_id=CUSTOMER_ID,
            operations=create_ops,
        )
        print(f"✅ {len(response.results)}件の曜日スケジュールを設定しました。")
        for result in response.results:
            print(f"    {result.resource_name}")
    except Exception as e:
        print(f"❌ エラー: {e}")


def set_hour_bid_adjustments(client, hour_json: str,
                              dry_run: bool = False, confirm: bool = False):
    """時間帯別入札調整を設定（全曜日共通）"""
    campaign_rn, campaign_name, campaign_id = _get_active_campaign_id(client)
    if not campaign_rn:
        print("⚠️  有効なキャンペーンが見つかりません。")
        return

    try:
        hour_schedule = json.loads(hour_json)
    except json.JSONDecodeError as e:
        print(f"⚠️  JSONパースエラー: {e}")
        return

    desc = f"キャンペーン「{campaign_name}」の時間帯別入札調整:\n" + \
           "\n".join(f"    - {h}時: {v:+d}%" for h, v in hour_schedule.items())
    if not _confirm_action(desc, dry_run, confirm):
        return

    # 既存スケジュールを削除
    service = client.get_service("GoogleAdsService")
    campaign_criterion_service = client.get_service("CampaignCriterionService")

    query = f"""
        SELECT campaign_criterion.resource_name
        FROM campaign_criterion
        WHERE campaign_criterion.campaign = '{campaign_rn}'
            AND campaign_criterion.type = 'AD_SCHEDULE'
    """
    remove_ops = []
    try:
        response = service.search_stream(customer_id=CUSTOMER_ID, query=query)
        for batch in response:
            for row in batch.results:
                op = client.get_type("CampaignCriterionOperation")
                op.remove = row.campaign_criterion.resource_name
                remove_ops.append(op)
    except Exception:
        pass

    if remove_ops:
        try:
            campaign_criterion_service.mutate_campaign_criteria(
                customer_id=CUSTOMER_ID,
                operations=remove_ops,
            )
            print(f"  🗑️  既存スケジュール {len(remove_ops)}件を削除しました。")
        except Exception as e:
            print(f"  ⚠️ 既存スケジュール削除失敗: {e}")

    # 時間帯ごとに全曜日のスケジュールを作成
    all_days = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]
    create_ops = []

    for hour_range, adj_percent in hour_schedule.items():
        parts = hour_range.split("-")
        if len(parts) != 2:
            print(f"  ⚠️ 不正な時間帯フォーマット: {hour_range} (例: '3-6')")
            continue
        try:
            start_hour = int(parts[0])
            end_hour = int(parts[1])
        except ValueError:
            print(f"  ⚠️ 不正な時間帯: {hour_range}")
            continue

        for day in all_days:
            op = client.get_type("CampaignCriterionOperation")
            criterion = op.create
            criterion.campaign = campaign_rn
            criterion.bid_modifier = 1.0 + (adj_percent / 100.0)
            criterion.ad_schedule.day_of_week = client.enums.DayOfWeekEnum[day]
            criterion.ad_schedule.start_hour = start_hour
            criterion.ad_schedule.start_minute = client.enums.MinuteOfHourEnum.ZERO
            criterion.ad_schedule.end_hour = end_hour
            criterion.ad_schedule.end_minute = client.enums.MinuteOfHourEnum.ZERO
            create_ops.append(op)

    if not create_ops:
        print("⚠️  設定するスケジュールがありません。")
        return

    try:
        response = campaign_criterion_service.mutate_campaign_criteria(
            customer_id=CUSTOMER_ID,
            operations=create_ops,
        )
        print(f"✅ {len(response.results)}件の時間帯スケジュールを設定しました。")
    except Exception as e:
        print(f"❌ エラー: {e}")


# ============================================================
# CSV フォールバック（既存機能）
# ============================================================

def parse_number(s):
    if not s or s == "--":
        return 0.0
    return float(s.replace(",", "").replace("%", "").replace("¥", ""))


def read_campaign_csv(filepath):
    campaigns = []
    with open(filepath, encoding="utf-8-sig") as f:
        lines = f.readlines()
    period_line = lines[1].strip()
    reader = csv.DictReader(lines[2:])
    for row in reader:
        campaigns.append({
            "name": row.get("キャンペーン", ""),
            "status": row.get("キャンペーンの状態", ""),
            "type": row.get("キャンペーン タイプ", ""),
            "clicks": int(parse_number(row.get("クリック数", "0"))),
            "impressions": int(parse_number(row.get("表示回数", "0"))),
            "ctr": parse_number(row.get("クリック率", "0")),
            "cpc": parse_number(row.get("平均クリック単価", "0")),
            "cost": parse_number(row.get("費用", "0")),
            "top_is": parse_number(row.get("最上部インプレッションの割合", "0")),
            "abs_top_is": parse_number(row.get("上部インプレッションの割合", "0")),
            "conversions": parse_number(row.get("コンバージョン", "0")),
            "vt_conversions": parse_number(row.get("ビュースルー コンバージョン", "0")),
            "cpa": parse_number(row.get("コンバージョン単価", "0")),
            "cvr": parse_number(row.get("コンバージョン率", "0")),
        })
    return period_line, campaigns


def read_keyword_csv(filepath):
    keywords = []
    with open(filepath, encoding="utf-8-sig") as f:
        lines = f.readlines()
    reader = csv.DictReader(lines[2:])
    for row in reader:
        keywords.append({
            "keyword": row.get("検索キーワード", ""),
            "status": row.get("検索キーワードのステータス", ""),
            "match_type": row.get("検索キーワードのマッチタイプ", ""),
            "campaign": row.get("キャンペーン", ""),
            "clicks": int(parse_number(row.get("クリック数", "0"))),
            "impressions": int(parse_number(row.get("表示回数", "0"))),
            "ctr": parse_number(row.get("クリック率", "0")),
            "cpc": parse_number(row.get("平均クリック単価", "0")),
            "cost": parse_number(row.get("費用", "0")),
            "top_is": parse_number(row.get("最上部インプレッションの割合", "0")),
            "abs_top_is": parse_number(row.get("上部インプレッションの割合", "0")),
            "conversions": parse_number(row.get("コンバージョン", "0")),
            "cpa": parse_number(row.get("コンバージョン単価", "0")),
            "cvr": parse_number(row.get("コンバージョン率", "0")),
        })
    return keywords


# ============================================================
# 分析ロジック
# ============================================================

def analyze(campaigns, keywords, adgroups):
    findings = []
    warnings = []

    total_cost = sum(c["cost"] for c in campaigns)
    total_clicks = sum(c["clicks"] for c in campaigns)
    total_imp = sum(c["impressions"] for c in campaigns)
    total_conv = sum(c["conversions"] for c in campaigns)
    avg_ctr = (total_clicks / total_imp * 100) if total_imp > 0 else 0
    avg_cpc = (total_cost / total_clicks) if total_clicks > 0 else 0
    avg_cpa = (total_cost / total_conv) if total_conv > 0 else 0
    avg_cvr = (total_conv / total_clicks * 100) if total_clicks > 0 else 0

    findings.append({
        "title": "全体概況",
        "metrics": {
            "費用": f"¥{total_cost:,.0f}",
            "クリック": f"{total_clicks:,}",
            "IMP": f"{total_imp:,}",
            "CTR": f"{avg_ctr:.2f}%",
            "CPC": f"¥{avg_cpc:,.0f}",
            "CV": f"{total_conv:,.1f}",
            "CVR": f"{avg_cvr:.2f}%",
            "CPA": f"¥{avg_cpa:,.0f}",
        }
    })

    if avg_cvr > 100:
        warnings.append({
            "level": "CRITICAL",
            "title": "コンバージョン計測異常",
            "detail": f"CVR {avg_cvr:.0f}%は物理的に不可能。コンバージョンアクション設定を確認。",
        })
    elif avg_cvr > 30:
        warnings.append({
            "level": "WARNING",
            "title": "CVRが異常に高い",
            "detail": f"CVR {avg_cvr:.1f}%。二重計測の可能性。",
        })

    if avg_ctr >= BENCH["ctr"] * 1.5:
        findings.append({
            "title": "CTR評価",
            "detail": f"CTR {avg_ctr:.2f}%はベンチマーク{BENCH['ctr']}%の{avg_ctr/BENCH['ctr']:.1f}倍。"
        })
    elif avg_ctr < BENCH["ctr"]:
        warnings.append({
            "level": "WARNING",
            "title": "CTRがベンチマーク以下",
            "detail": f"CTR {avg_ctr:.2f}% < ベンチマーク{BENCH['ctr']}%。広告コピー改善を検討。",
        })

    for c in campaigns:
        if c["top_is"] > 0 and c["top_is"] < 30:
            warnings.append({
                "level": "WARNING",
                "title": f"最上部IS低い: {c['name']}",
                "detail": f"最上部IS {c['top_is']:.1f}%。入札強化 or 品質スコア改善で拡大可能。",
            })

    active_kw = [k for k in keywords if k["status"] == "有効" and k["clicks"] > 0]
    if keywords and len(active_kw) <= 2:
        warnings.append({
            "level": "WARNING",
            "title": f"アクティブKWが{len(active_kw)}語のみ",
            "detail": "KW拡張で分散を推奨。",
        })

    if active_kw and total_cost > 0:
        top_kw = max(active_kw, key=lambda k: k["cost"])
        concentration = top_kw["cost"] / total_cost * 100
        if concentration > 80:
            warnings.append({
                "level": "WARNING",
                "title": f"KW集中: 「{top_kw['keyword']}」に{concentration:.0f}%",
                "detail": "1語への依存度が高い。",
            })

    return findings, warnings


# ============================================================
# 改善提案（週次・月次用）
# ============================================================

def generate_suggestions(campaigns, keywords, adgroups):
    """データに基づいて改善提案を生成"""
    suggestions = []

    total_cost = sum(c["cost"] for c in campaigns)
    total_clicks = sum(c["clicks"] for c in campaigns)
    total_imp = sum(c["impressions"] for c in campaigns)
    total_conv = sum(c["conversions"] for c in campaigns)
    avg_ctr = (total_clicks / total_imp * 100) if total_imp > 0 else 0
    avg_cpc = (total_cost / total_clicks) if total_clicks > 0 else 0
    avg_cpa = (total_cost / total_conv) if total_conv > 0 else 0
    avg_cvr = (total_conv / total_clicks * 100) if total_clicks > 0 else 0

    active_kw = [k for k in keywords if k.get("clicks", 0) > 0]

    # 1. CVR異常
    if avg_cvr > 100:
        suggestions.append({
            "priority": "緊急",
            "category": "コンバージョン設定",
            "issue": f"CVR {avg_cvr:.0f}%は計測異常。session_start等が「メイン」に含まれている可能性。",
            "action": "Google Ads「目標→コンバージョン」で主要コンバージョンアクションを確認。本登録のみ「メイン」に設定。",
        })
    elif avg_cvr > 30:
        suggestions.append({
            "priority": "高",
            "category": "コンバージョン設定",
            "issue": f"CVR {avg_cvr:.1f}%は高すぎる。二重計測またはマイクロコンバージョン混入の可能性。",
            "action": "コンバージョンアクション一覧を確認し、本登録以外が「メイン」になっていないかチェック。",
        })

    # 2. CPA評価
    if total_conv > 0 and avg_cvr <= 100:
        if avg_cpa > BENCH["cpa"] * 1.5:
            suggestions.append({
                "priority": "高",
                "category": "コスト効率",
                "issue": f"CPA ¥{avg_cpa:,.0f}が目標¥{BENCH['cpa']:,}の{avg_cpa/BENCH['cpa']:.1f}倍。",
                "action": "低パフォーマンスKWの一時停止、ネガティブKW追加、LPの改善を検討。",
            })
        elif avg_cpa <= BENCH["cpa"] * 0.8:
            suggestions.append({
                "priority": "中",
                "category": "スケール",
                "issue": f"CPA ¥{avg_cpa:,.0f}が目標以下で効率的。予算拡大の余地あり。",
                "action": "予算を10-20%段階的に増額。インプレッションシェアが低いキャンペーンから優先。",
            })

    # 3. インプレッションシェア
    for c in campaigns:
        if c.get("search_is", 0) > 0 and c["search_is"] < 50:
            suggestions.append({
                "priority": "高",
                "category": "表示機会の損失",
                "issue": f"「{c['name']}」の検索IS {c['search_is']:.0f}% — 半分以上の検索機会を逃している。",
                "action": "予算制限による損失なら予算増額、ランク不足なら品質スコア改善 or 入札引き上げ。",
            })
        elif c.get("top_is", 0) > 0 and c["top_is"] < 20:
            suggestions.append({
                "priority": "中",
                "category": "掲載順位",
                "issue": f"「{c['name']}」の最上部IS {c['top_is']:.1f}% — 上位表示の機会が少ない。",
                "action": "入札強化または広告品質（見出し・LP関連性）の改善で上位表示率を向上。",
            })

    # 4. KW集中リスク
    if active_kw and total_cost > 0:
        top_kw = max(active_kw, key=lambda k: k["cost"])
        concentration = top_kw["cost"] / total_cost * 100
        if concentration > 70:
            suggestions.append({
                "priority": "中",
                "category": "キーワード分散",
                "issue": f"「{top_kw['keyword']}」に費用の{concentration:.0f}%が集中。単一障害点リスク。",
                "action": "関連KWを完全一致で追加して分散。シニア系・目的別KWの拡張を検討。",
            })

    # 5. KW別パフォーマンス分析
    if active_kw:
        # 高CTR・低CVのKW
        for kw in active_kw:
            if kw["clicks"] >= 20 and kw["ctr"] > 10 and kw["conversions"] == 0:
                suggestions.append({
                    "priority": "高",
                    "category": "KW最適化",
                    "issue": f"「{kw['keyword']}」CTR {kw['ctr']:.1f}%だがCV 0件。クリックは取れるが登録に繋がらない。",
                    "action": "LP到達後の離脱が原因の可能性。LPとの関連性を確認、または一時停止を検討。",
                })

        # 高CVR・低費用のKW（拡大余地）
        high_cvr_kw = [k for k in active_kw if k["conversions"] > 0 and k["cvr"] > 15 and k["cost"] < total_cost * 0.1]
        if high_cvr_kw:
            names = "、".join(f"「{k['keyword']}」CVR{k['cvr']:.0f}%" for k in high_cvr_kw[:3])
            suggestions.append({
                "priority": "中",
                "category": "KWスケール",
                "issue": f"高CVRだが費用比率が低いKW: {names}",
                "action": "入札を引き上げてインプレッションを拡大。フレーズ一致での追加も検討。",
            })

    # 6. CPC上昇チェック
    if avg_cpc > BENCH["cpc"] * 1.5:
        suggestions.append({
            "priority": "中",
            "category": "入札コスト",
            "issue": f"平均CPC ¥{avg_cpc:,.0f}がベンチマーク¥{BENCH['cpc']:,}の{avg_cpc/BENCH['cpc']:.1f}倍。",
            "action": "競合が増えている可能性。品質スコア改善（広告関連性・LP品質）でCPC低減を図る。",
        })

    # 7. キャンペーン構造
    if len(campaigns) == 1:
        suggestions.append({
            "priority": "中",
            "category": "アカウント構造",
            "issue": "キャンペーンが1つのみ。ブランド/非ブランド/競合の分離なし。",
            "action": "ブランドKWを別キャンペーンに分離し、非ブランドKWと異なる入札戦略を適用。",
        })

    if not suggestions:
        suggestions.append({
            "priority": "-",
            "category": "総合",
            "issue": "現状大きな問題は見つかりません。",
            "action": "引き続きデータを蓄積し、次回レポートで再評価。",
        })

    return suggestions


# ============================================================
# 高度な分析提案（検索語句・時間帯・デバイス・広告・地域）
# ============================================================

DAY_MAP = {
    "MONDAY": "月", "TUESDAY": "火", "WEDNESDAY": "水",
    "THURSDAY": "木", "FRIDAY": "金", "SATURDAY": "土", "SUNDAY": "日",
}

HOUR_BLOCKS = [(0, 3), (3, 6), (6, 9), (9, 12), (12, 15), (15, 18), (18, 21), (21, 24)]

DEVICE_MAP = {
    "MOBILE": "モバイル", "DESKTOP": "PC", "TABLET": "タブレット",
    "CONNECTED_TV": "TV", "OTHER": "その他",
}


def generate_advanced_suggestions(search_terms, hourly_data, device_data, ad_data, geo_data):
    """検索語句・時間帯・デバイス・広告・地域データから改善提案を生成"""
    suggestions = []

    # --- 検索語句分析 ---
    if search_terms:
        # 追加KW候補: CV実績ありだが未登録
        add_candidates = [
            t for t in search_terms
            if t["conversions"] > 0 and t["status"] != "ADDED"
        ]
        add_candidates.sort(key=lambda t: t["conversions"], reverse=True)
        if add_candidates:
            top_terms = [f"「{t['search_term']}」(CV{t['conversions']:.0f})" for t in add_candidates[:5]]
            suggestions.append({
                "priority": "高",
                "category": "検索語句（追加候補）",
                "issue": f"CV実績があるが未登録の検索語句: {', '.join(top_terms)}",
                "action": "完全一致またはフレーズ一致でキーワード追加し、入札を最適化。",
            })

        # 除外KW候補: クリック消化だがCV 0
        exclude_candidates = [
            t for t in search_terms
            if t["clicks"] >= 5 and t["conversions"] == 0
        ]
        exclude_candidates.sort(key=lambda t: t["cost"], reverse=True)
        if exclude_candidates:
            top_waste = [f"「{t['search_term']}」(¥{t['cost']:,.0f})" for t in exclude_candidates[:5]]
            suggestions.append({
                "priority": "高",
                "category": "検索語句（除外候補）",
                "issue": f"費用だけ消化しCV 0の検索語句: {', '.join(top_waste)}",
                "action": "除外キーワードに追加して無駄な費用を削減。",
            })

    # --- 曜日×時間帯分析 ---
    if hourly_data:
        # 曜日別集計
        day_agg = {}
        for row in hourly_data:
            day = row["day_of_week"]
            if day not in day_agg:
                day_agg[day] = {"clicks": 0, "conversions": 0, "cost": 0}
            day_agg[day]["clicks"] += row["clicks"]
            day_agg[day]["conversions"] += row["conversions"]
            day_agg[day]["cost"] += row["cost"]

        # CVRで最良/最悪の曜日（最低10クリック）
        qualified_days = {d: v for d, v in day_agg.items() if v["clicks"] >= 10}
        if qualified_days:
            for d in qualified_days:
                qualified_days[d]["cvr"] = (qualified_days[d]["conversions"] / qualified_days[d]["clicks"] * 100) if qualified_days[d]["clicks"] > 0 else 0

            best_day = max(qualified_days.items(), key=lambda x: x[1]["cvr"])
            worst_day = min(qualified_days.items(), key=lambda x: x[1]["cvr"])

            best_jp = DAY_MAP.get(best_day[0], best_day[0])
            worst_jp = DAY_MAP.get(worst_day[0], worst_day[0])

            if best_day[1]["cvr"] > 0 and worst_day[1]["cvr"] == 0 and worst_day[1]["cost"] > 500:
                suggestions.append({
                    "priority": "中",
                    "category": "曜日最適化",
                    "issue": f"最良曜日: {best_jp}(CVR {best_day[1]['cvr']:.1f}%) / 最悪: {worst_jp}(CVR 0%, 費用¥{worst_day[1]['cost']:,.0f})",
                    "action": f"{worst_jp}曜の入札を引き下げ、{best_jp}曜の入札を強化。広告スケジュール調整を検討。",
                })

        # 時間帯別集計（3時間ブロック）
        hour_agg = {}
        for row in hourly_data:
            for start, end in HOUR_BLOCKS:
                if start <= row["hour"] < end:
                    block_key = f"{start}-{end}"
                    if block_key not in hour_agg:
                        hour_agg[block_key] = {"clicks": 0, "conversions": 0, "cost": 0}
                    hour_agg[block_key]["clicks"] += row["clicks"]
                    hour_agg[block_key]["conversions"] += row["conversions"]
                    hour_agg[block_key]["cost"] += row["cost"]
                    break

        qualified_hours = {h: v for h, v in hour_agg.items() if v["clicks"] >= 5}
        if qualified_hours:
            for h in qualified_hours:
                qualified_hours[h]["cvr"] = (qualified_hours[h]["conversions"] / qualified_hours[h]["clicks"] * 100) if qualified_hours[h]["clicks"] > 0 else 0

            zero_cvr_hours = [(h, v) for h, v in qualified_hours.items() if v["cvr"] == 0 and v["cost"] > 500]
            if zero_cvr_hours:
                zero_cvr_hours.sort(key=lambda x: x[1]["cost"], reverse=True)
                waste_hours = ", ".join(f"{h}時(¥{v['cost']:,.0f})" for h, v in zero_cvr_hours[:3])
                suggestions.append({
                    "priority": "中",
                    "category": "時間帯最適化",
                    "issue": f"CVR 0%で費用消化している時間帯: {waste_hours}",
                    "action": "広告スケジュールで該当時間帯の入札を引き下げまたは停止。",
                })

    # --- デバイス分析 ---
    if device_data:
        for d in device_data:
            device_name = DEVICE_MAP.get(d["device"], d["device"])
            if d["clicks"] > 20 and d["conversions"] == 0:
                suggestions.append({
                    "priority": "高",
                    "category": "デバイス最適化",
                    "issue": f"{device_name}で{d['clicks']}クリック / CV 0件 (費用¥{d['cost']:,.0f})",
                    "action": f"{device_name}の入札単価を-50%〜-100%に調整。",
                })

        # 最良デバイス
        best_device = [d for d in device_data if d["clicks"] >= 10 and d["cvr"] > 0]
        if best_device:
            best = max(best_device, key=lambda x: x["cvr"])
            device_name = DEVICE_MAP.get(best["device"], best["device"])
            suggestions.append({
                "priority": "中",
                "category": "デバイス強化",
                "issue": f"{device_name}が最高CVR {best['cvr']:.1f}% ({best['conversions']:.0f}CV)",
                "action": f"{device_name}の入札を強化。LP表示速度やUIも{device_name}向けに最適化。",
            })

    # --- 広告分析 ---
    if ad_data and len(ad_data) >= 2:
        ads_with_clicks = [a for a in ad_data if a["clicks"] >= 5]
        if len(ads_with_clicks) >= 2:
            best_ad = max(ads_with_clicks, key=lambda a: a["ctr"])
            worst_ad = min(ads_with_clicks, key=lambda a: a["ctr"])
            if best_ad["ctr"] > worst_ad["ctr"] * 1.5:
                suggestions.append({
                    "priority": "中",
                    "category": "広告文最適化",
                    "issue": f"広告CTR差: 最高 {best_ad['ctr']:.1f}% vs 最低 {worst_ad['ctr']:.1f}%",
                    "action": f"低CTR広告を一時停止し、高CTR広告の見出しパターンを参考に新規広告を作成。",
                })

    # --- 地域分析 ---
    if geo_data:
        geo_with_clicks = [g for g in geo_data if g["clicks"] >= 5]
        for g in geo_with_clicks:
            g["cvr"] = (g["conversions"] / g["clicks"] * 100) if g["clicks"] > 0 else 0

        if len(geo_with_clicks) >= 2:
            best_geo = max(geo_with_clicks, key=lambda g: g["cvr"])
            worst_geo = min(geo_with_clicks, key=lambda g: g["cvr"])
            if best_geo["cvr"] > 0 and worst_geo["cvr"] == 0 and worst_geo["cost"] > 500:
                suggestions.append({
                    "priority": "中",
                    "category": "地域最適化",
                    "issue": f"最良地域: {best_geo['location']}(CVR {best_geo['cvr']:.1f}%) / 最悪: {worst_geo['location']}(CVR 0%, 費用¥{worst_geo['cost']:,.0f})",
                    "action": f"{worst_geo['location']}の入札を引き下げ、{best_geo['location']}への予算配分を増加。",
                })

    return suggestions


# ============================================================
# HTML出力（週次・月次）
# ============================================================

def export_html(period, campaigns, keywords, findings, warnings, suggestions, out_dir, report_type="weekly",
                search_terms=None, hourly_data=None, device_data=None, ad_data=None, geo_data=None):
    """HTMLレポート出力"""
    out_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.date.today().isoformat()
    prefix = "週次" if report_type == "weekly" else "月次"
    filename = out_dir / f"{prefix}レポート_{date_str}.html"

    total_cost = sum(c["cost"] for c in campaigns)
    total_clicks = sum(c["clicks"] for c in campaigns)
    total_imp = sum(c["impressions"] for c in campaigns)
    total_conv = sum(c["conversions"] for c in campaigns)
    avg_ctr = (total_clicks / total_imp * 100) if total_imp > 0 else 0
    avg_cpc = (total_cost / total_clicks) if total_clicks > 0 else 0
    avg_cpa = (total_cost / total_conv) if total_conv > 0 else 0
    avg_cvr = (total_conv / total_clicks * 100) if total_clicks > 0 else 0

    # キャンペーン別テーブル
    campaign_rows = ""
    for c in sorted(campaigns, key=lambda x: x["cost"], reverse=True):
        campaign_rows += f"""<tr>
            <td>{c['name']}</td>
            <td class="num">¥{c['cost']:,.0f}</td>
            <td class="num">{c['impressions']:,}</td>
            <td class="num">{c['clicks']:,}</td>
            <td class="num">{c['ctr']:.2f}%</td>
            <td class="num">¥{c['cpc']:,.0f}</td>
            <td class="num">{c['conversions']:,.1f}</td>
            <td class="num">{c['cvr']:.1f}%</td>
            <td class="num">¥{c['cpa']:,.0f}</td>
            <td class="num">{c.get('top_is', 0):.1f}%</td>
        </tr>"""

    # KW別テーブル
    active_kw = [k for k in keywords if k.get("clicks", 0) > 0]
    kw_rows = ""
    for kw in sorted(active_kw, key=lambda x: x["cost"], reverse=True):
        share = (kw["cost"] / total_cost * 100) if total_cost > 0 else 0
        cvr_class = "warn" if kw["cvr"] > 50 else ("good" if kw["conversions"] > 0 else "")
        kw_rows += f"""<tr>
            <td>{kw['keyword']}</td>
            <td>{kw['match_type']}</td>
            <td class="num">¥{kw['cost']:,.0f}</td>
            <td class="num">{share:.0f}%</td>
            <td class="num">{kw['impressions']:,}</td>
            <td class="num">{kw['clicks']}</td>
            <td class="num">{kw['ctr']:.1f}%</td>
            <td class="num">¥{kw['cpc']:,.0f}</td>
            <td class="num {cvr_class}">{kw['conversions']:,.1f}</td>
            <td class="num {cvr_class}">{kw['cvr']:.1f}%</td>
            <td class="num">¥{kw['cpa']:,.0f}</td>
        </tr>"""

    # 警告
    warnings_html = ""
    for w in warnings:
        icon = "🚨" if w["level"] == "CRITICAL" else "⚠️"
        cls = "critical" if w["level"] == "CRITICAL" else "warning"
        warnings_html += f"""<div class="alert {cls}">
            <strong>{icon} {w['title']}</strong>
            <p>{w['detail']}</p>
        </div>"""

    # 改善提案
    suggestions_html = ""
    for s in suggestions:
        pri_cls = {"緊急": "pri-critical", "高": "pri-high", "中": "pri-mid"}.get(s["priority"], "pri-low")
        suggestions_html += f"""<div class="suggestion">
            <div class="suggestion-header">
                <span class="{pri_cls}">[{s['priority']}]</span>
                <strong>{s['category']}</strong>
            </div>
            <p class="issue">{s['issue']}</p>
            <p class="action">→ {s['action']}</p>
        </div>"""

    # --- 新規分析セクションHTML ---
    advanced_sections_html = ""

    # 検索語句分析
    if search_terms:
        add_candidates = sorted(
            [t for t in search_terms if t["conversions"] > 0 and t["status"] != "ADDED"],
            key=lambda t: t["conversions"], reverse=True
        )[:10]
        exclude_candidates = sorted(
            [t for t in search_terms if t["clicks"] >= 5 and t["conversions"] == 0],
            key=lambda t: t["cost"], reverse=True
        )[:10]

        st_html = ""
        if add_candidates:
            add_rows = ""
            for t in add_candidates:
                add_rows += f"""<tr>
                    <td>{t['search_term']}</td>
                    <td class="num">{t['clicks']}</td>
                    <td class="num">{t['ctr']:.1f}%</td>
                    <td class="num good">{t['conversions']:.0f}</td>
                    <td class="num">{t['cvr']:.1f}%</td>
                    <td class="num">¥{t['cost']:,.0f}</td>
                </tr>"""
            st_html += f"""<h3 style="color:#1e8e3e; margin:16px 0 8px;">追加KW候補（CV実績あり）</h3>
            <table>
              <thead><tr>
                <th>検索語句</th><th class="num">Click</th><th class="num">CTR</th>
                <th class="num">CV</th><th class="num">CVR</th><th class="num">費用</th>
              </tr></thead>
              <tbody>{add_rows}</tbody>
            </table>"""

        if exclude_candidates:
            exc_rows = ""
            for t in exclude_candidates:
                exc_rows += f"""<tr>
                    <td>{t['search_term']}</td>
                    <td class="num">{t['clicks']}</td>
                    <td class="num">{t['ctr']:.1f}%</td>
                    <td class="num warn">0</td>
                    <td class="num warn">0%</td>
                    <td class="num warn">¥{t['cost']:,.0f}</td>
                </tr>"""
            st_html += f"""<h3 style="color:#d93025; margin:16px 0 8px;">除外KW候補（費用消化のみ）</h3>
            <table>
              <thead><tr>
                <th>検索語句</th><th class="num">Click</th><th class="num">CTR</th>
                <th class="num">CV</th><th class="num">CVR</th><th class="num">費用</th>
              </tr></thead>
              <tbody>{exc_rows}</tbody>
            </table>"""

        if st_html:
            advanced_sections_html += f"""<div class="section">
              <h2>検索語句分析</h2>
              {st_html}
            </div>"""

    # 曜日×時間帯分析
    if hourly_data:
        # 曜日別集計
        day_agg = {}
        for row in hourly_data:
            day = row["day_of_week"]
            if day not in day_agg:
                day_agg[day] = {"clicks": 0, "conversions": 0, "cost": 0, "impressions": 0}
            day_agg[day]["clicks"] += row["clicks"]
            day_agg[day]["conversions"] += row["conversions"]
            day_agg[day]["cost"] += row["cost"]
            day_agg[day]["impressions"] += row["impressions"]

        day_order = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]
        day_rows = ""
        for d in day_order:
            if d in day_agg:
                v = day_agg[d]
                cvr = (v["conversions"] / v["clicks"] * 100) if v["clicks"] > 0 else 0
                cpa = (v["cost"] / v["conversions"]) if v["conversions"] > 0 else 0
                day_jp = DAY_MAP.get(d, d)
                day_rows += f"""<tr>
                    <td>{day_jp}</td>
                    <td class="num">{v['clicks']}</td>
                    <td class="num">{v['conversions']:.0f}</td>
                    <td class="num">{cvr:.1f}%</td>
                    <td class="num">{"¥" + f"{cpa:,.0f}" if v['conversions'] > 0 else "-"}</td>
                    <td class="num">¥{v['cost']:,.0f}</td>
                </tr>"""

        # 時間帯別集計
        hour_agg = {}
        for row in hourly_data:
            for start, end in HOUR_BLOCKS:
                if start <= row["hour"] < end:
                    block_key = f"{start}-{end}"
                    if block_key not in hour_agg:
                        hour_agg[block_key] = {"clicks": 0, "conversions": 0, "cost": 0}
                    hour_agg[block_key]["clicks"] += row["clicks"]
                    hour_agg[block_key]["conversions"] += row["conversions"]
                    hour_agg[block_key]["cost"] += row["cost"]
                    break

        hour_rows = ""
        for start, end in HOUR_BLOCKS:
            block_key = f"{start}-{end}"
            if block_key in hour_agg:
                v = hour_agg[block_key]
                cvr = (v["conversions"] / v["clicks"] * 100) if v["clicks"] > 0 else 0
                hour_rows += f"""<tr>
                    <td>{start}:00〜{end}:00</td>
                    <td class="num">{v['clicks']}</td>
                    <td class="num">{v['conversions']:.0f}</td>
                    <td class="num">{cvr:.1f}%</td>
                    <td class="num">¥{v['cost']:,.0f}</td>
                </tr>"""

        dh_html = f"""<h3 style="margin:0 0 8px;">曜日別パフォーマンス</h3>
        <table>
          <thead><tr>
            <th>曜日</th><th class="num">Click</th><th class="num">CV</th>
            <th class="num">CVR</th><th class="num">CPA</th><th class="num">費用</th>
          </tr></thead>
          <tbody>{day_rows}</tbody>
        </table>
        <h3 style="margin:24px 0 8px;">時間帯別パフォーマンス</h3>
        <table>
          <thead><tr>
            <th>時間帯</th><th class="num">Click</th><th class="num">CV</th>
            <th class="num">CVR</th><th class="num">費用</th>
          </tr></thead>
          <tbody>{hour_rows}</tbody>
        </table>"""

        advanced_sections_html += f"""<div class="section">
          <h2>曜日×時間帯分析</h2>
          {dh_html}
        </div>"""

    # デバイス別分析
    if device_data:
        dev_rows = ""
        for d in sorted(device_data, key=lambda x: x["cost"], reverse=True):
            device_name = DEVICE_MAP.get(d["device"], d["device"])
            cpa = (d["cost"] / d["conversions"]) if d["conversions"] > 0 else 0
            dev_rows += f"""<tr>
                <td>{device_name}</td>
                <td class="num">{d['impressions']:,}</td>
                <td class="num">{d['clicks']}</td>
                <td class="num">{d['ctr']:.1f}%</td>
                <td class="num">{d['conversions']:.0f}</td>
                <td class="num">{d['cvr']:.1f}%</td>
                <td class="num">{"¥" + f"{cpa:,.0f}" if d['conversions'] > 0 else "-"}</td>
                <td class="num">¥{d['cost']:,.0f}</td>
            </tr>"""

        advanced_sections_html += f"""<div class="section">
          <h2>デバイス別パフォーマンス</h2>
          <table>
            <thead><tr>
              <th>デバイス</th><th class="num">IMP</th><th class="num">Click</th>
              <th class="num">CTR</th><th class="num">CV</th><th class="num">CVR</th>
              <th class="num">CPA</th><th class="num">費用</th>
            </tr></thead>
            <tbody>{dev_rows}</tbody>
          </table>
        </div>"""

    # 広告別パフォーマンス
    if ad_data:
        ad_sorted = sorted([a for a in ad_data if a["clicks"] > 0], key=lambda a: a["clicks"], reverse=True)
        if ad_sorted:
            ad_rows = ""
            for a in ad_sorted[:20]:
                cpa = (a["cost"] / a["conversions"]) if a["conversions"] > 0 else 0
                headline_preview = a["headlines"][:50] + ("..." if len(a["headlines"]) > 50 else "")
                ad_rows += f"""<tr>
                    <td title="{a['headlines']}">{headline_preview}</td>
                    <td class="num">{a['clicks']}</td>
                    <td class="num">{a['ctr']:.1f}%</td>
                    <td class="num">{a['conversions']:.0f}</td>
                    <td class="num">{a['cvr']:.1f}%</td>
                    <td class="num">{"¥" + f"{cpa:,.0f}" if a['conversions'] > 0 else "-"}</td>
                </tr>"""

            advanced_sections_html += f"""<div class="section">
              <h2>広告別パフォーマンス</h2>
              <table>
                <thead><tr>
                  <th>見出し</th><th class="num">Click</th><th class="num">CTR</th>
                  <th class="num">CV</th><th class="num">CVR</th><th class="num">CPA</th>
                </tr></thead>
                <tbody>{ad_rows}</tbody>
              </table>
            </div>"""

    # 地域別パフォーマンス
    if geo_data:
        geo_sorted = sorted([g for g in geo_data if g["clicks"] > 0], key=lambda g: g["clicks"], reverse=True)
        if geo_sorted:
            geo_rows = ""
            for g in geo_sorted[:20]:
                cvr = (g["conversions"] / g["clicks"] * 100) if g["clicks"] > 0 else 0
                cpa = (g["cost"] / g["conversions"]) if g["conversions"] > 0 else 0
                geo_rows += f"""<tr>
                    <td>{g['location']}</td>
                    <td class="num">{g['clicks']}</td>
                    <td class="num">{g['conversions']:.0f}</td>
                    <td class="num">{cvr:.1f}%</td>
                    <td class="num">{"¥" + f"{cpa:,.0f}" if g['conversions'] > 0 else "-"}</td>
                    <td class="num">¥{g['cost']:,.0f}</td>
                </tr>"""

            advanced_sections_html += f"""<div class="section">
              <h2>地域別パフォーマンス</h2>
              <table>
                <thead><tr>
                  <th>地域</th><th class="num">Click</th><th class="num">CV</th>
                  <th class="num">CVR</th><th class="num">CPA</th><th class="num">費用</th>
                </tr></thead>
                <tbody>{geo_rows}</tbody>
              </table>
            </div>"""

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Google Ads レポート — {period}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, "Hiragino Sans", sans-serif;
         background: #f5f5f5; color: #333; padding: 20px; }}
  .container {{ max-width: 1100px; margin: 0 auto; }}
  h1 {{ text-align: center; margin-bottom: 5px; font-size: 22px; }}
  .period {{ text-align: center; color: #888; margin-bottom: 30px; font-size: 14px; }}
  .section {{ background: #fff; border-radius: 8px; padding: 24px;
              margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
  h2 {{ font-size: 16px; margin-bottom: 16px; padding-bottom: 8px;
        border-bottom: 2px solid #1a73e8; color: #1a73e8; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ background: #f8f9fa; text-align: left; padding: 10px 8px;
       border-bottom: 2px solid #dee2e6; font-weight: 600; }}
  td {{ padding: 8px; border-bottom: 1px solid #eee; }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  tr:hover {{ background: #f8f9fa; }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }}
  .kpi {{ text-align: center; padding: 16px; background: #f8f9fa; border-radius: 8px; }}
  .kpi .value {{ font-size: 28px; font-weight: 700; color: #1a73e8; }}
  .kpi .label {{ font-size: 12px; color: #888; margin-top: 4px; }}
  .alert {{ padding: 12px 16px; margin-bottom: 10px; border-radius: 8px; }}
  .alert.critical {{ background: #fce8e6; border-left: 4px solid #d93025; }}
  .alert.warning {{ background: #fef7e0; border-left: 4px solid #f9ab00; }}
  .alert p {{ font-size: 13px; color: #555; margin-top: 4px; }}
  .suggestion {{ padding: 16px; border-left: 4px solid #1a73e8; margin-bottom: 12px;
                 background: #f8f9fa; border-radius: 0 8px 8px 0; }}
  .suggestion-header {{ margin-bottom: 8px; }}
  .pri-critical {{ color: #d93025; font-weight: 700; }}
  .pri-high {{ color: #e8710a; font-weight: 700; }}
  .pri-mid {{ color: #f9ab00; font-weight: 700; }}
  .pri-low {{ color: #888; }}
  .issue {{ color: #555; margin-bottom: 6px; font-size: 13px; }}
  .action {{ color: #1a73e8; font-size: 13px; font-weight: 500; }}
  .good {{ color: #1e8e3e; font-weight: 600; }}
  .warn {{ color: #e8710a; font-weight: 600; }}
  .footer {{ text-align: center; color: #aaa; font-size: 11px; margin-top: 30px; }}
  @media (max-width: 768px) {{
    .kpi-grid {{ grid-template-columns: repeat(2, 1fr); }}
    table {{ font-size: 11px; }}
  }}
</style>
</head>
<body>
<div class="container">
  <h1>Google Ads パフォーマンスレポート</h1>
  <p class="period">{period}</p>

  <div class="kpi-grid">
    <div class="kpi"><div class="value">¥{total_cost:,.0f}</div><div class="label">総費用</div></div>
    <div class="kpi"><div class="value">{total_clicks:,}</div><div class="label">クリック (CTR {avg_ctr:.1f}%)</div></div>
    <div class="kpi"><div class="value">{total_conv:,.0f}</div><div class="label">CV (CVR {avg_cvr:.1f}%)</div></div>
    <div class="kpi"><div class="value">¥{avg_cpa:,.0f}</div><div class="label">CPA (目標¥{BENCH['cpa']:,})</div></div>
  </div>

  {"<div class='section'><h2>警告</h2>" + warnings_html + "</div>" if warnings_html else ""}

  <div class="section">
    <h2>キャンペーン別</h2>
    <table>
      <thead><tr>
        <th>キャンペーン</th><th class="num">費用</th><th class="num">IMP</th>
        <th class="num">Click</th><th class="num">CTR</th><th class="num">CPC</th>
        <th class="num">CV</th><th class="num">CVR</th><th class="num">CPA</th>
        <th class="num">最上部IS</th>
      </tr></thead>
      <tbody>{campaign_rows}</tbody>
    </table>
  </div>

  <div class="section">
    <h2>キーワード別</h2>
    <table>
      <thead><tr>
        <th>キーワード</th><th>マッチ</th><th class="num">費用</th><th class="num">比率</th>
        <th class="num">IMP</th><th class="num">Click</th><th class="num">CTR</th>
        <th class="num">CPC</th><th class="num">CV</th><th class="num">CVR</th>
        <th class="num">CPA</th>
      </tr></thead>
      <tbody>{kw_rows}</tbody>
    </table>
  </div>

  {advanced_sections_html}

  <div class="section">
    <h2>改善提案 ({len(suggestions)}件)</h2>
    {suggestions_html}
  </div>

  <p class="footer">Generated by TrustLink Google Ads Report — {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
</div>
</body>
</html>"""

    with open(filename, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"🌐 HTML: {filename}")
    return filename


# ============================================================
# LINE通知
# ============================================================

def build_line_message(period, campaigns, keywords, warnings, suggestions=None, search_terms=None):
    total_cost = sum(c["cost"] for c in campaigns)
    total_clicks = sum(c["clicks"] for c in campaigns)
    total_imp = sum(c["impressions"] for c in campaigns)
    total_conv = sum(c["conversions"] for c in campaigns)
    avg_ctr = (total_clicks / total_imp * 100) if total_imp > 0 else 0
    avg_cpc = (total_cost / total_clicks) if total_clicks > 0 else 0
    avg_cpa = (total_cost / total_conv) if total_conv > 0 else 0
    avg_cvr = (total_conv / total_clicks * 100) if total_clicks > 0 else 0

    lines = [
        "📊 Google Ads レポート",
        f"📅 {period}",
        "",
        f"💰 費用: ¥{total_cost:,.0f}",
        f"👆 {total_clicks:,}cl (CTR {avg_ctr:.1f}%)",
        f"💵 CPC: ¥{avg_cpc:,.0f}",
    ]

    if avg_cvr <= 100:
        lines.append(f"🎯 CV: {total_conv:,.1f} (CVR {avg_cvr:.1f}%)")
        lines.append(f"📈 CPA: ¥{avg_cpa:,.0f}")
    else:
        lines.append(f"🚨 CV計測異常 ({total_conv:,.0f}件 / CVR {avg_cvr:.0f}%)")

    if campaigns and campaigns[0].get("top_is", 0) > 0:
        lines.append(f"👁 最上部IS: {campaigns[0]['top_is']:.1f}%")

    # KW別
    active_kw = [k for k in keywords if k.get("clicks", 0) > 0]
    if active_kw:
        lines.append("")
        lines.append("🔑 KW別:")
        for kw in sorted(active_kw, key=lambda k: k["cost"], reverse=True)[:5]:
            share = (kw["cost"] / total_cost * 100) if total_cost > 0 else 0
            lines.append(
                f"  「{kw['keyword']}」"
                f" {kw['clicks']}cl CTR{kw['ctr']:.1f}%"
                f" ¥{kw['cost']:,.0f}({share:.0f}%)"
            )

    # 検索語句サマリー（週次・月次のみ）
    if search_terms:
        add_cands = sorted(
            [t for t in search_terms if t["conversions"] > 0 and t["status"] != "ADDED"],
            key=lambda t: t["conversions"], reverse=True
        )[:3]
        exc_cands = sorted(
            [t for t in search_terms if t["clicks"] >= 5 and t["conversions"] == 0],
            key=lambda t: t["cost"], reverse=True
        )[:3]
        if add_cands or exc_cands:
            lines.append("")
            lines.append("🔍 検索語句:")
            if add_cands:
                terms_str = "".join(f"「{t['search_term']}」" for t in add_cands)
                lines.append(f"  追加候補: {terms_str}(CV実績あり)")
            if exc_cands:
                terms_str = "".join(f"「{t['search_term']}」" for t in exc_cands)
                lines.append(f"  除外候補: {terms_str}(費用だけ消化)")

    # 警告
    critical = [w for w in warnings if w["level"] == "CRITICAL"]
    warning_items = [w for w in warnings if w["level"] == "WARNING"]

    if critical:
        lines.append("")
        for w in critical:
            lines.append(f"🚨 {w['title']}")

    if warning_items:
        lines.append("")
        lines.append(f"⚠️ 注意 ({len(warning_items)}件):")
        for w in warning_items[:5]:
            lines.append(f"  ・{w['title']}")

    # 改善提案サマリー（週次・月次のみ）
    if suggestions:
        high_pri = [s for s in suggestions if s["priority"] in ("緊急", "高")]
        mid_pri = [s for s in suggestions if s["priority"] == "中"]
        lines.append("")
        lines.append(f"💡 改善提案 ({len(suggestions)}件):")
        for s in high_pri[:3]:
            lines.append(f"  🔴 [{s['priority']}] {s['category']}: {s['issue'][:40]}")
        for s in mid_pri[:2]:
            lines.append(f"  🟡 {s['category']}: {s['issue'][:40]}")
        if len(suggestions) > 5:
            lines.append(f"  ...他{len(suggestions)-5}件 → HTMLレポート参照")
        lines.append("")
        lines.append(f"📄 詳細HTML → Googleドライブ:")
        lines.append(f"  広告関連/マッチング/Google広告/レポート/")

    # ベンチマーク
    lines.append("")
    lines.append(f"{'✅' if avg_ctr >= BENCH['ctr'] else '🔴'} CTR: {avg_ctr:.1f}% (基準{BENCH['ctr']}%)")
    if avg_cvr <= 100:
        lines.append(f"{'✅' if avg_cvr >= BENCH['cvr'] else '🔴'} CVR: {avg_cvr:.1f}% (基準{BENCH['cvr']}%)")

    return "\n".join(lines)


def send_discord(message):
    if not DISCORD_MARKETING_WEBHOOK:
        print("⚠️  DISCORD_MARKETING_WEBHOOK が未設定。Discord通知をスキップ。")
        return False

    chunks = [message[i:i + 1900] for i in range(0, len(message), 1900)]
    for chunk in chunks:
        payload = json.dumps({"content": chunk}).encode()
        req = urllib.request.Request(
            DISCORD_MARKETING_WEBHOOK,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "TrustLink-AdReport/1.0",
            },
            method="POST",
        )
        try:
            urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            print(f"⚠️  Discord通知エラー: {e.code} {body}")
            return False
        except Exception as e:
            print(f"⚠️  Discord通知エラー: {e}")
            return False
    print("📱 Discord通知を送信しました")
    return True


def send_line(message):
    if not LINE_CHANNEL_TOKEN:
        print("⚠️  LINE_CHANNEL_TOKEN が未設定。LINE通知をスキップ。")
        return False

    payload = json.dumps({
        "messages": [{"type": "text", "text": message}],
    }).encode()

    req = urllib.request.Request(
        "https://api.line.me/v2/bot/message/broadcast",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LINE_CHANNEL_TOKEN}",
        },
    )
    try:
        urllib.request.urlopen(req)
        print("📱 LINE通知を送信しました")
        return True
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"⚠️  LINE通知エラー: {e.code} {body}")
        return False
    except Exception as e:
        print(f"⚠️  LINE通知エラー: {e}")
        return False


# ============================================================
# ターミナル出力
# ============================================================

def print_report(period, findings, warnings):
    print(f"\n{'=' * 70}")
    print(f"  Google Ads パフォーマンスレポート  |  {period}")
    print(f"{'=' * 70}\n")

    for f in findings:
        print(f"📊 {f['title']}")
        if "metrics" in f:
            for k, v in f["metrics"].items():
                print(f"  {k}: {v}")
        if "detail" in f:
            print(f"  {f['detail']}")
        print()

    if warnings:
        print(f"⚠️  警告 ({len(warnings)}件)")
        print("-" * 50)
        for w in warnings:
            icon = "🚨" if w["level"] == "CRITICAL" else "⚠️"
            print(f"  {icon} [{w['level']}] {w['title']}")
            print(f"     {w['detail']}")
            print()

    print(f"{'=' * 70}\n")


# ============================================================
# メイン
# ============================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Google Ads レポート生成")
    parser.add_argument("--notify", action="store_true", help="LINE通知を送信")
    parser.add_argument("--date", type=str, help="対象日 YYYY-MM-DD（デフォルト: 昨日）")
    parser.add_argument("--since", type=str, help="開始日 YYYY-MM-DD")
    parser.add_argument("--until", type=str, help="終了日 YYYY-MM-DD")
    parser.add_argument("--days", type=int, help="過去N日間")
    parser.add_argument("--csv", action="store_true", help="CSV読み込みモード（API不使用）")
    parser.add_argument("--dir", type=str, default=str(REPORT_DIR), help="CSVディレクトリ")

    # --- Mutation（書き込み）操作 ---
    parser.add_argument("--list-conversions", action="store_true",
                        help="コンバージョンアクション一覧を表示")
    parser.add_argument("--set-secondary", nargs="+", metavar="NAME",
                        help="指定コンバージョンをセカンダリに変更（部分一致）")
    parser.add_argument("--add-negative", nargs="+", metavar="KEYWORD",
                        help="除外キーワードを追加（キャンペーンレベル）")
    parser.add_argument("--remove-negative", nargs="+", metavar="KEYWORD",
                        help="除外キーワードを削除（キャンペーンレベル）")
    parser.add_argument("--negative-list", type=str, metavar="LIST_NAME",
                        help="共有除外キーワードリスト名（--add-negativeと併用）")
    parser.add_argument("--add-keyword", nargs="+", metavar="KEYWORD",
                        help="キーワードを広告グループに追加")
    parser.add_argument("--match", type=str, default="exact",
                        choices=["exact", "phrase", "broad"],
                        help="キーワードのマッチタイプ（デフォルト: exact）")
    parser.add_argument("--set-bidding", type=str, metavar="STRATEGY",
                        help="入札戦略を変更 (maximize_conversions, maximize_clicks, target_cpa, manual_cpc)")
    parser.add_argument("--max-cpc", type=int, metavar="YEN",
                        help="上限CPC（円）-- set-biddingと併用")
    parser.add_argument("--target-cpa", type=int, metavar="YEN",
                        help="目標CPA（円）-- set-biddingと併用")
    parser.add_argument("--set-schedule", type=str, metavar="JSON",
                        help='曜日別入札調整 JSON (例: \'{"SUNDAY": -20, "THURSDAY": 15}\')')
    parser.add_argument("--set-hour-bid", type=str, metavar="JSON",
                        help='時間帯別入札調整 JSON (例: \'{"3-6": -30, "6-15": 20}\')')
    parser.add_argument("--dry-run", action="store_true",
                        help="変更を実行せず、内容のみ表示")
    parser.add_argument("--confirm", action="store_true",
                        help="確認プロンプトをスキップして実行")

    args = parser.parse_args()

    # --- Mutation コマンドのディスパッチ ---
    mutation_requested = any([
        args.list_conversions,
        args.set_secondary,
        args.add_negative,
        args.remove_negative,
        args.add_keyword,
        args.set_bidding,
        args.set_schedule,
        args.set_hour_bid,
    ])

    if mutation_requested:
        try:
            client = get_google_ads_client()
        except Exception as e:
            print(f"⚠️  APIクライアント初期化エラー: {e}")
            return

        if args.list_conversions:
            list_conversion_actions(client)
            return

        if args.set_secondary:
            set_conversions_secondary(client, args.set_secondary,
                                      dry_run=args.dry_run, confirm=args.confirm)
            return

        if args.add_negative:
            add_negative_keywords(client, args.add_negative,
                                   negative_list_name=args.negative_list,
                                   dry_run=args.dry_run, confirm=args.confirm)
            return

        if args.remove_negative:
            remove_negative_keywords(client, args.remove_negative,
                                      dry_run=args.dry_run, confirm=args.confirm)
            return

        if args.add_keyword:
            add_keywords(client, args.add_keyword, match_type=args.match,
                         dry_run=args.dry_run, confirm=args.confirm)
            return

        if args.set_bidding:
            set_bidding_strategy(client, args.set_bidding,
                                 max_cpc=args.max_cpc, target_cpa=args.target_cpa,
                                 dry_run=args.dry_run, confirm=args.confirm)
            return

        if args.set_schedule:
            set_ad_schedule_bid_adjustments(client, args.set_schedule,
                                            dry_run=args.dry_run, confirm=args.confirm)
            return

        if args.set_hour_bid:
            set_hour_bid_adjustments(client, args.set_hour_bid,
                                     dry_run=args.dry_run, confirm=args.confirm)
            return

    today = datetime.date.today()

    # 期間の決定
    if args.since and args.until:
        since = args.since
        until = args.until
    elif args.days:
        until = (today - datetime.timedelta(days=1)).isoformat()
        since = (today - datetime.timedelta(days=args.days)).isoformat()
    elif args.date:
        since = args.date
        until = args.date
    else:
        since = (today - datetime.timedelta(days=1)).isoformat()
        until = since

    period = since if since == until else f"{since} 〜 {until}"

    campaigns = []
    keywords = []
    adgroups = []

    if args.csv:
        report_dir = Path(args.dir)
        campaign_file = report_dir / "キャンペーンのパフォーマンス.csv"
        keyword_file = report_dir / "検索キーワード.csv"

        if not campaign_file.exists():
            print(f"⚠️  {campaign_file} が見つかりません。")
            return

        print(f"\n📡 CSVからデータ読み込み中...")
        period, campaigns = read_campaign_csv(campaign_file)
        if keyword_file.exists():
            keywords = read_keyword_csv(keyword_file)
    else:
        print(f"\n📡 Google Ads API からデータ取得中... ({period})")
        try:
            client = get_google_ads_client()
            campaigns = fetch_campaign_data(client, since, until)
            keywords = fetch_keyword_data(client, since, until)
            adgroups = fetch_adgroup_data(client, since, until)
        except Exception as e:
            print(f"⚠️  APIエラー: {e}")
            print("--csv オプションでCSV読み込みモードに切り替え可能です。")
            return

    if not campaigns:
        print(f"⚠️  {period} のデータがありません。")
        return

    # 分析
    findings, warnings = analyze(campaigns, keywords, adgroups)
    is_multiday = since != until

    # 週次・月次は改善提案 + HTML出力 + 高度分析
    suggestions = None
    search_terms = []
    hourly_data = []
    device_data = []
    ad_data = []
    geo_data = []

    if is_multiday:
        suggestions = generate_suggestions(campaigns, keywords, adgroups)

        # 高度分析データ取得（各フェッチは独立、失敗しても他に影響しない）
        if not args.csv:
            try:
                search_terms = fetch_search_terms(client, since, until)
                print(f"  検索語句: {len(search_terms)}件取得")
            except Exception as e:
                print(f"  ⚠️ 検索語句取得失敗: {e}")

            try:
                hourly_data = fetch_hourly_data(client, since, until)
                print(f"  曜日×時間帯: {len(hourly_data)}件取得")
            except Exception as e:
                print(f"  ⚠️ 曜日×時間帯取得失敗: {e}")

            try:
                device_data = fetch_device_data(client, since, until)
                print(f"  デバイス別: {len(device_data)}件取得")
            except Exception as e:
                print(f"  ⚠️ デバイス別取得失敗: {e}")

            try:
                ad_data = fetch_ad_data(client, since, until)
                print(f"  広告別: {len(ad_data)}件取得")
            except Exception as e:
                print(f"  ⚠️ 広告別取得失敗: {e}")

            try:
                geo_data = fetch_geo_data(client, since, until)
                print(f"  地域別: {len(geo_data)}件取得")
            except Exception as e:
                print(f"  ⚠️ 地域別取得失敗: {e}")

            # 高度分析から追加提案を生成
            advanced = generate_advanced_suggestions(search_terms, hourly_data, device_data, ad_data, geo_data)
            suggestions.extend(advanced)

        days_diff = (datetime.date.fromisoformat(until) - datetime.date.fromisoformat(since)).days
        report_type = "monthly" if days_diff > 14 else "weekly"
        sub_folder = "月次" if report_type == "monthly" else "週次"
        out_dir = GDRIVE_REPORT_DIR / sub_folder
        export_html(period, campaigns, keywords, findings, warnings, suggestions, out_dir, report_type,
                    search_terms=search_terms, hourly_data=hourly_data, device_data=device_data,
                    ad_data=ad_data, geo_data=geo_data)

    # ターミナル出力
    print_report(period, findings, warnings)
    if suggestions:
        print(f"💡 改善提案 ({len(suggestions)}件)")
        print("-" * 50)
        for s in suggestions:
            print(f"  [{s['priority']}] {s['category']}")
            print(f"     {s['issue']}")
            print(f"     → {s['action']}")
            print()

    # 通知（Discord優先、フォールバックでLINE）
    if args.notify:
        msg = build_line_message(period, campaigns, keywords, warnings, suggestions,
                                 search_terms=search_terms)
        print("\n--- 送信メッセージ ---")
        print(msg)
        print("--- ここまで ---\n")
        send_discord(msg)

    print("✅ レポート生成完了\n")


if __name__ == "__main__":
    main()
