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

load_dotenv(Path(__file__).parent / ".env")

# Google Ads API
DEVELOPER_TOKEN = os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN")
CLIENT_ID = os.getenv("GOOGLE_ADS_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_ADS_CLIENT_SECRET")
REFRESH_TOKEN = os.getenv("GOOGLE_ADS_REFRESH_TOKEN")
CUSTOMER_ID = os.getenv("GOOGLE_ADS_CUSTOMER_ID")
LOGIN_CUSTOMER_ID = os.getenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID")

# LINE
LINE_CHANNEL_TOKEN = os.getenv("LINE_CHANNEL_TOKEN")

REPORT_DIR = Path(__file__).parent / "report"

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


def fetch_campaign_data(client, date_str):
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
            metrics.search_absolute_top_impression_share
        FROM campaign
        WHERE segments.date = '{date_str}'
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
            })

    return campaigns


def fetch_keyword_data(client, date_str):
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
        WHERE segments.date = '{date_str}'
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


def fetch_adgroup_data(client, date_str):
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
        WHERE segments.date = '{date_str}'
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
# LINE通知
# ============================================================

def build_line_message(period, campaigns, keywords, warnings):
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

    # ベンチマーク
    lines.append("")
    lines.append(f"{'✅' if avg_ctr >= BENCH['ctr'] else '🔴'} CTR: {avg_ctr:.1f}% (基準{BENCH['ctr']}%)")
    if avg_cvr <= 100:
        lines.append(f"{'✅' if avg_cvr >= BENCH['cvr'] else '🔴'} CVR: {avg_cvr:.1f}% (基準{BENCH['cvr']}%)")

    return "\n".join(lines)


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
    parser.add_argument("--csv", action="store_true", help="CSV読み込みモード（API不使用）")
    parser.add_argument("--dir", type=str, default=str(REPORT_DIR), help="CSVディレクトリ")
    args = parser.parse_args()

    # 対象日
    if args.date:
        target_date = args.date
    else:
        target_date = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()

    campaigns = []
    keywords = []
    adgroups = []
    period = target_date

    if args.csv:
        # CSVフォールバック
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
        # API取得
        print(f"\n📡 Google Ads API からデータ取得中... ({target_date})")
        try:
            client = get_google_ads_client()
            campaigns = fetch_campaign_data(client, target_date)
            keywords = fetch_keyword_data(client, target_date)
            adgroups = fetch_adgroup_data(client, target_date)
        except Exception as e:
            print(f"⚠️  APIエラー: {e}")
            print("--csv オプションでCSV読み込みモードに切り替え可能です。")
            return

    if not campaigns:
        print(f"⚠️  {target_date} のデータがありません。")
        return

    # 分析
    findings, warnings = analyze(campaigns, keywords, adgroups)

    # ターミナル出力
    print_report(period, findings, warnings)

    # LINE通知
    if args.notify:
        msg = build_line_message(period, campaigns, keywords, warnings)
        print("\n--- LINE送信メッセージ ---")
        print(msg)
        print("--- ここまで ---\n")
        send_line(msg)

    print("✅ レポート生成完了\n")


if __name__ == "__main__":
    main()
