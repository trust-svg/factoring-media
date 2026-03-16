"""
TrustLink — Meta広告 パフォーマンスレポート
広告レベルの成果をサイト別に集計し、改善案を自動生成します。
出力: ターミナル / CSV / HTML / PDF
"""

import os
import sys
import csv
import json
import datetime
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
from dotenv import load_dotenv
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount

load_dotenv()

ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")
AD_ACCOUNT_ID = os.getenv("META_AD_ACCOUNT_ID")
OLIVE_ADSET_ID = os.getenv("OLIVE_ADSET_ID")
TRAVIS_ADSET_ID = os.getenv("TRAVIS_ADSET_ID")
MASSIVE_ADSET_ID = os.getenv("MASSIVE_ADSET_ID")

ADSET_TO_SITE = {
    OLIVE_ADSET_ID: "Olive",
    TRAVIS_ADSET_ID: "Travis",
    MASSIVE_ADSET_ID: "Massive",
}

# 業界ベンチマーク（マッチング系）
BENCH = {
    "ctr": 1.0,       # %
    "cpc": 150,        # 円
    "cvr": 5.0,        # %
    "cpa": 1000,       # 円
}

FIELDS = [
    "ad_id", "ad_name", "adset_id", "adset_name",
    "campaign_name", "impressions", "clicks", "ctr",
    "cpc", "spend", "actions", "cost_per_action_type",
]


def init_api():
    FacebookAdsApi.init(access_token=ACCESS_TOKEN)
    return AdAccount(AD_ACCOUNT_ID)


def fetch_ad_insights(account, since, until):
    """広告レベルのインサイトを取得"""
    params = {
        "time_range": {"since": since, "until": until},
        "level": "ad",
        "filtering": [{"field": "ad.effective_status", "operator": "IN",
                        "value": ["ACTIVE", "PAUSED"]}],
    }
    insights = account.get_insights(fields=FIELDS, params=params)
    return list(insights)


def parse_conversions(row):
    """actionsから登録数・課金数・CPAを抽出（重複回避）"""
    actions = row.get("actions") or []
    cost_per = row.get("cost_per_action_type") or []

    action_map = {a["action_type"]: int(a.get("value", 0)) for a in actions}
    cost_map = {c["action_type"]: float(c.get("value", 0)) for c in cost_per}

    def pick(pixel_key, generic_key):
        if pixel_key in action_map:
            return action_map[pixel_key]
        return action_map.get(generic_key, 0)

    registrations = pick("offsite_conversion.fb_pixel_complete_registration", "complete_registration")
    leads = pick("offsite_conversion.fb_pixel_lead", "lead")
    purchases = pick("offsite_conversion.fb_pixel_purchase", "purchase")

    conversions = registrations + leads  # 登録系のみ

    cpa = 0
    for pixel_key, generic_key in [
        ("offsite_conversion.fb_pixel_complete_registration", "complete_registration"),
        ("offsite_conversion.fb_pixel_lead", "lead"),
    ]:
        if pixel_key in cost_map:
            cpa = cost_map[pixel_key]
            break
        elif generic_key in cost_map:
            cpa = cost_map[generic_key]
            break

    return conversions, purchases, cpa


def classify_ad(row_data):
    """勝ち/負け/判定不能をラベル付け"""
    imp = row_data["impressions"]
    ctr = row_data["ctr"]
    cvr = row_data["cvr"]

    if imp < 500:
        return "⏳ データ不足"

    score = 0
    if ctr >= BENCH["ctr"]:
        score += 1
    if row_data["cpc"] <= BENCH["cpc"] and row_data["cpc"] > 0:
        score += 1
    if cvr >= BENCH["cvr"]:
        score += 1
    if row_data["cpa"] <= BENCH["cpa"] and row_data["cpa"] > 0:
        score += 1

    if score >= 3:
        return "🏆 勝ち"
    elif score >= 2:
        return "📊 普通"
    else:
        return "❌ 負け"


def generate_analysis(rows):
    """現状の分析を生成"""
    analysis = []

    total_spend = sum(r["spend"] for r in rows)
    total_imp = sum(r["impressions"] for r in rows)
    total_clicks = sum(r["clicks"] for r in rows)
    total_conv = sum(r["conversions"] for r in rows)
    total_purch = sum(r["purchases"] for r in rows)
    avg_ctr = (total_clicks / total_imp * 100) if total_imp > 0 else 0
    avg_cpa = (total_spend / total_conv) if total_conv > 0 else 0
    purch_rate = (total_purch / total_conv * 100) if total_conv > 0 else 0

    # 1. 全体概況
    cpa_ratio = avg_cpa / BENCH["cpa"] if BENCH["cpa"] > 0 else 0
    if cpa_ratio <= 1:
        status = "目標CPA達成中"
        status_icon = "✅"
    elif cpa_ratio <= 1.5:
        status = "目標CPAの1.5倍以内"
        status_icon = "⚠️"
    else:
        status = f"目標CPAの{cpa_ratio:.1f}倍"
        status_icon = "🔴"

    analysis.append({
        "title": "全体概況",
        "body": f"{status_icon} {status}（目標¥{BENCH['cpa']:,} → 実績¥{avg_cpa:,.0f}）\n"
                f"総消化¥{total_spend:,.0f} / 登録{total_conv}件 / 課金{total_purch}件 / "
                f"登録→課金率 {purch_rate:.1f}%"
    })

    # 2. サイト別評価
    site_data = {}
    for r in rows:
        s = r["site"]
        if s not in site_data:
            site_data[s] = {"spend": 0, "conv": 0, "purch": 0, "clicks": 0, "imp": 0}
        site_data[s]["spend"] += r["spend"]
        site_data[s]["conv"] += r["conversions"]
        site_data[s]["purch"] += r["purchases"]
        site_data[s]["clicks"] += r["clicks"]
        site_data[s]["imp"] += r["impressions"]

    site_lines = []
    for site, d in sorted(site_data.items(), key=lambda x: x[1]["spend"], reverse=True):
        cpa = (d["spend"] / d["conv"]) if d["conv"] > 0 else float("inf")
        pr = (d["purch"] / d["conv"] * 100) if d["conv"] > 0 else 0
        ctr = (d["clicks"] / d["imp"] * 100) if d["imp"] > 0 else 0
        icon = "✅" if cpa <= BENCH["cpa"] else ("⚠️" if cpa <= BENCH["cpa"] * 2 else "🔴")
        site_lines.append(
            f"  {icon} {site}: CPA¥{cpa:,.0f} / CTR{ctr:.1f}% / "
            f"登録{d['conv']}→課金{d['purch']}（{pr:.0f}%）"
        )

    analysis.append({
        "title": "サイト別評価",
        "body": "\n".join(site_lines)
    })

    # 3. 広告効率（上位・下位）
    active = [r for r in rows if r["impressions"] >= 500 and r["conversions"] > 0]
    if active:
        best = min(active, key=lambda r: r["cpa"])
        worst = max(active, key=lambda r: r["cpa"])
        analysis.append({
            "title": "広告効率",
            "body": f"  最良: {best['ad_name']}（{best['site']}）CPA¥{best['cpa']:,.0f}\n"
                    f"  最悪: {worst['ad_name']}（{worst['site']}）CPA¥{worst['cpa']:,.0f}\n"
                    f"  差は{worst['cpa']/best['cpa']:.1f}倍 — 最悪の広告の予算を最良に振り替えるだけで効率改善の余地あり"
        })

    # 4. 課金転換分析
    if total_purch > 0:
        sites_with_purch = [s for s, d in site_data.items() if d["purch"] > 0]
        sites_without = [s for s, d in site_data.items() if d["purch"] == 0 and d["conv"] > 0]
        body = f"課金実績があるサイト: {', '.join(sites_with_purch)}"
        if sites_without:
            body += f"\n  課金0のサイト: {', '.join(sites_without)} — LP/サイト導線の問題 or データ蓄積期間不足の可能性"
        cost_per_purch = total_spend / total_purch
        body += f"\n  課金1件あたりの広告費: ¥{cost_per_purch:,.0f}"
        analysis.append({"title": "課金転換", "body": body})
    else:
        analysis.append({
            "title": "課金転換",
            "body": "課金実績なし — ピクセルイベントの設定確認 or データ蓄積期間が短い可能性"
        })

    # 5. データ充足度
    sufficient = [r for r in rows if r["impressions"] >= 500]
    insufficient = [r for r in rows if r["impressions"] < 500]
    analysis.append({
        "title": "データ充足度",
        "body": f"判定可能: {len(sufficient)}本 / データ不足: {len(insufficient)}本\n"
                f"  データ不足の広告は予算が分散している可能性。広告本数を絞って集中配信を検討。"
    })

    return analysis


def generate_suggestions(rows):
    """データに基づいて改善提案を生成"""
    suggestions = []

    # サイト別集計
    site_spend = {}
    site_conv = {}
    for r in rows:
        site = r["site"]
        site_spend[site] = site_spend.get(site, 0) + r["spend"]
        site_conv[site] = site_conv.get(site, 0) + r["conversions"]

    # 全体CTR
    total_clicks = sum(r["clicks"] for r in rows)
    total_imp = sum(r["impressions"] for r in rows)
    avg_ctr = (total_clicks / total_imp * 100) if total_imp > 0 else 0

    # 全体CPA
    total_spend = sum(r["spend"] for r in rows)
    total_conv = sum(r["conversions"] for r in rows)
    avg_cpa = (total_spend / total_conv) if total_conv > 0 else 0

    # --- 改善提案ロジック ---

    # 1. CTR低い広告
    low_ctr = [r for r in rows if r["impressions"] >= 500 and r["ctr"] < BENCH["ctr"] * 0.7]
    if low_ctr:
        names = ", ".join(r["ad_name"] for r in low_ctr[:3])
        suggestions.append({
            "category": "クリエイティブ",
            "priority": "高",
            "issue": f"CTRが低い広告が{len(low_ctr)}本あります（{names}）",
            "action": "メインテキストの冒頭を変更するか、画像を差し替えてテスト。"
                      "特に最初の1行で「自分ごと」にさせる表現に変更。",
        })

    # 2. CPC高い広告
    high_cpc = [r for r in rows if r["cpc"] > BENCH["cpc"] * 1.5 and r["impressions"] >= 500]
    if high_cpc:
        names = ", ".join(r["ad_name"] for r in high_cpc[:3])
        suggestions.append({
            "category": "入札・コスト",
            "priority": "高",
            "issue": f"CPCが高い広告: {names}（¥{int(max(r['cpc'] for r in high_cpc))}）",
            "action": "ターゲティングが狭すぎないか確認。オーディエンス拡大 or 類似拡張を検討。",
        })

    # 3. CVゼロの広告（十分なインプレッション）
    no_cv = [r for r in rows if r["conversions"] == 0 and r["impressions"] >= 1000]
    if no_cv:
        names = ", ".join(r["ad_name"] for r in no_cv[:3])
        suggestions.append({
            "category": "コンバージョン",
            "priority": "高",
            "issue": f"1000imp以上でCV0の広告: {names}",
            "action": "LP到達後の離脱が原因の可能性。LP改善 or 広告→LPのメッセージ一致度を見直し。"
                      "改善しない場合はOFFにして予算を勝ち広告に集中。",
        })

    # 4. 勝ち広告のスケール提案
    winners = [r for r in rows if r["label"] == "🏆 勝ち"]
    if winners:
        names = ", ".join(r["ad_name"] for r in winners)
        suggestions.append({
            "category": "スケール",
            "priority": "中",
            "issue": f"勝ち広告が{len(winners)}本あります（{names}）",
            "action": "勝ち広告のバリエーションを作成（見出し変更、画像差替え）してテスト。"
                      "予算を20%ずつ段階的に増額。",
        })

    # 5. 停止推奨の広告
    stop_ads = []
    watch_ads = []
    for r in rows:
        if r["impressions"] < 500:
            continue
        # CPA目標の3倍超 + 課金ゼロ → 即停止
        if r["cpa"] > BENCH["cpa"] * 3 and r["purchases"] == 0:
            stop_ads.append(r)
        # 1000imp以上で登録ゼロ → 即停止
        elif r["impressions"] >= 1000 and r["conversions"] == 0:
            stop_ads.append(r)
        # CPA目標の2倍超 + 課金ゼロ → 要注意
        elif r["cpa"] > BENCH["cpa"] * 2 and r["purchases"] == 0:
            watch_ads.append(r)

    if stop_ads:
        stop_ads.sort(key=lambda x: x["spend"], reverse=True)
        lines = []
        for r in stop_ads:
            lines.append(f"  {r['ad_name']}（{r['site']}）消化¥{r['spend']:,.0f} / CPA¥{r['cpa']:,.0f} / 課金{r['purchases']}")
        suggestions.insert(0, {
            "category": "即停止すべき広告",
            "priority": "高",
            "issue": f"以下の{len(stop_ads)}本は予算を浪費しています:\n" + "\n".join(lines),
            "action": "即OFFにして、浮いた予算を勝ち広告（CPA¥1,000以下）に集中配分。",
        })

    if watch_ads:
        watch_ads.sort(key=lambda x: x["spend"], reverse=True)
        lines = []
        for r in watch_ads:
            lines.append(f"  {r['ad_name']}（{r['site']}）消化¥{r['spend']:,.0f} / CPA¥{r['cpa']:,.0f} / 課金{r['purchases']}")
        suggestions.insert(len(stop_ads) and 1 or 0, {
            "category": "要注意（1週間改善なければ停止）",
            "priority": "中",
            "issue": f"以下の{len(watch_ads)}本はCPA目標の2倍超かつ課金ゼロ:\n" + "\n".join(lines),
            "action": "クリエイティブ or LPを変更して1週間テスト。改善しなければOFF。",
        })

    # 6. サイト間比較
    if len(site_spend) >= 2:
        best_site = None
        best_cpa = float("inf")
        worst_site = None
        worst_cpa = 0
        for site, spend in site_spend.items():
            conv = site_conv.get(site, 0)
            cpa = (spend / conv) if conv > 0 else float("inf")
            if cpa < best_cpa:
                best_cpa = cpa
                best_site = site
            if cpa > worst_cpa and conv > 0:
                worst_cpa = cpa
                worst_site = site

        if best_site and worst_site and best_site != worst_site:
            suggestions.append({
                "category": "予算配分",
                "priority": "中",
                "issue": f"{best_site}のCPAが最良（¥{int(best_cpa)}）、{worst_site}が最高（¥{int(worst_cpa)}）",
                "action": f"{worst_site}の予算を{best_site}にシフトすることを検討。"
                          f"ただし{worst_site}の広告クリエイティブ改善も並行して実施。",
            })

    # 6. 全体的なデータ不足
    insufficient = [r for r in rows if r["impressions"] < 500]
    if len(insufficient) > len(rows) * 0.5:
        suggestions.append({
            "category": "データ蓄積",
            "priority": "中",
            "issue": f"{len(insufficient)}/{len(rows)}本がデータ不足（500imp未満）",
            "action": "判定に最低500imp（理想1000imp）必要。広告本数を絞って予算を集中させるか、期間を延ばして再評価。",
        })

    # 7. 全体CTRが低い場合
    if avg_ctr < BENCH["ctr"] * 0.8 and total_imp > 1000:
        suggestions.append({
            "category": "全体戦略",
            "priority": "高",
            "issue": f"全体CTRが{avg_ctr:.2f}%（ベンチマーク{BENCH['ctr']}%）",
            "action": "画像のインパクトが弱い可能性。人物写真やビフォーアフター系のクリエイティブをテスト。"
                      "また、ターゲット年齢層の精度を確認。",
        })

    if not suggestions:
        suggestions.append({
            "category": "総合",
            "priority": "-",
            "issue": "現状大きな問題は見つかりません",
            "action": "引き続きデータを蓄積し、次回レポートで再評価してください。",
        })

    return suggestions


def process_insights(insights):
    """インサイトデータを整形"""
    rows = []
    for row in insights:
        imp = int(row.get("impressions", 0))
        clicks = int(row.get("clicks", 0))
        ctr = float(row.get("ctr", 0))
        cpc = float(row.get("cpc", 0))
        spend = float(row.get("spend", 0))
        conversions, purchases, cpa = parse_conversions(row)
        cvr = (conversions / clicks * 100) if clicks > 0 else 0

        adset_id = row.get("adset_id", "")
        site = ADSET_TO_SITE.get(adset_id, "不明")

        r = {
            "ad_id": row.get("ad_id", ""),
            "ad_name": row.get("ad_name", ""),
            "adset_name": row.get("adset_name", ""),
            "campaign_name": row.get("campaign_name", ""),
            "site": site,
            "impressions": imp,
            "clicks": clicks,
            "ctr": ctr,
            "cpc": cpc,
            "spend": spend,
            "conversions": conversions,
            "purchases": purchases,
            "cvr": cvr,
            "cpa": cpa,
        }
        r["label"] = classify_ad(r)
        rows.append(r)

    # spend降順
    rows.sort(key=lambda x: x["spend"], reverse=True)
    return rows


def print_report(rows, analysis, suggestions, since, until):
    """ターミナル出力"""
    print(f"\n{'=' * 90}")
    print(f"  Facebook広告パフォーマンスレポート  |  {since} 〜 {until}")
    print(f"{'=' * 90}\n")

    # サイト別集計
    sites = {}
    for r in rows:
        s = r["site"]
        if s not in sites:
            sites[s] = {"spend": 0, "clicks": 0, "imp": 0, "conv": 0, "purch": 0}
        sites[s]["spend"] += r["spend"]
        sites[s]["clicks"] += r["clicks"]
        sites[s]["imp"] += r["impressions"]
        sites[s]["conv"] += r["conversions"]
        sites[s]["purch"] += r["purchases"]

    print("📊 サイト別サマリー")
    print(f"{'サイト':<10} {'消化額':>10} {'IMP':>8} {'Click':>7} {'CTR':>6} {'登録':>4} {'課金':>4} {'CPA':>8}")
    print("-" * 68)
    for site, d in sites.items():
        ctr = (d["clicks"] / d["imp"] * 100) if d["imp"] > 0 else 0
        cpa = (d["spend"] / d["conv"]) if d["conv"] > 0 else 0
        print(f"{site:<10} ¥{d['spend']:>9,.0f} {d['imp']:>8,} {d['clicks']:>7,} {ctr:>5.2f}% {d['conv']:>4} {d['purch']:>4} ¥{cpa:>7,.0f}")

    total_spend = sum(d["spend"] for d in sites.values())
    total_imp = sum(d["imp"] for d in sites.values())
    total_clicks = sum(d["clicks"] for d in sites.values())
    total_conv = sum(d["conv"] for d in sites.values())
    total_purch = sum(d["purch"] for d in sites.values())
    total_ctr = (total_clicks / total_imp * 100) if total_imp > 0 else 0
    total_cpa = (total_spend / total_conv) if total_conv > 0 else 0
    print("-" * 68)
    print(f"{'合計':<10} ¥{total_spend:>9,.0f} {total_imp:>8,} {total_clicks:>7,} {total_ctr:>5.2f}% {total_conv:>4} {total_purch:>4} ¥{total_cpa:>7,.0f}")

    # 広告別
    print(f"\n📋 広告別パフォーマンス")
    print(f"{'広告名':<30} {'サイト':<8} {'IMP':>7} {'CTR':>6} {'CPC':>7} {'登録':>4} {'課金':>4} {'CPA':>8} {'消化':>9} {'判定'}")
    print("-" * 110)
    for r in rows:
        print(f"{r['ad_name']:<30} {r['site']:<8} {r['impressions']:>7,} {r['ctr']:>5.2f}% ¥{r['cpc']:>6,.0f} {r['conversions']:>4} {r['purchases']:>4} ¥{r['cpa']:>7,.0f} ¥{r['spend']:>8,.0f} {r['label']}")

    # 現状分析
    print(f"\n🔍 現状分析")
    print("-" * 80)
    for a in analysis:
        print(f"\n  【{a['title']}】")
        for line in a["body"].split("\n"):
            print(f"  {line}")

    # 改善提案
    print(f"\n💡 改善提案（{len(suggestions)}件）")
    print("-" * 80)
    for i, s in enumerate(suggestions, 1):
        print(f"\n  [{s['priority']}] {s['category']}")
        print(f"  問題: {s['issue']}")
        print(f"  対策: {s['action']}")

    print(f"\n{'=' * 90}\n")


def export_csv(rows, since, until, out_dir):
    """CSV出力"""
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = out_dir / f"report_{since}_{until}.csv"
    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["広告名", "サイト", "キャンペーン", "広告セット",
                         "IMP", "Click", "CTR%", "CPC", "消化額",
                         "登録", "課金", "CVR%", "CPA", "判定"])
        for r in rows:
            writer.writerow([
                r["ad_name"], r["site"], r["campaign_name"], r["adset_name"],
                r["impressions"], r["clicks"], f"{r['ctr']:.2f}",
                f"{r['cpc']:.0f}", f"{r['spend']:.0f}",
                r["conversions"], r["purchases"], f"{r['cvr']:.2f}",
                f"{r['cpa']:.0f}", r["label"],
            ])
    print(f"📄 CSV: {filename}")
    return filename


def export_html(rows, analysis, suggestions, since, until, out_dir):
    """HTML出力"""
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = out_dir / f"report_{since}_{until}.html"

    # サイト別集計
    sites = {}
    for r in rows:
        s = r["site"]
        if s not in sites:
            sites[s] = {"spend": 0, "clicks": 0, "imp": 0, "conv": 0, "purch": 0}
        sites[s]["spend"] += r["spend"]
        sites[s]["clicks"] += r["clicks"]
        sites[s]["imp"] += r["impressions"]
        sites[s]["conv"] += r["conversions"]
        sites[s]["purch"] += r["purchases"]

    total_spend = sum(d["spend"] for d in sites.values())
    total_imp = sum(d["imp"] for d in sites.values())
    total_clicks = sum(d["clicks"] for d in sites.values())
    total_conv = sum(d["conv"] for d in sites.values())
    total_purch = sum(d["purch"] for d in sites.values())

    # サイト別行
    site_rows_html = ""
    for site, d in sites.items():
        ctr = (d["clicks"] / d["imp"] * 100) if d["imp"] > 0 else 0
        cpa = (d["spend"] / d["conv"]) if d["conv"] > 0 else 0
        site_rows_html += f"""<tr>
            <td>{site}</td>
            <td class="num">¥{d['spend']:,.0f}</td>
            <td class="num">{d['imp']:,}</td>
            <td class="num">{d['clicks']:,}</td>
            <td class="num">{ctr:.2f}%</td>
            <td class="num">{d['conv']}</td>
            <td class="num">{d['purch']}</td>
            <td class="num">¥{cpa:,.0f}</td>
        </tr>"""

    total_ctr = (total_clicks / total_imp * 100) if total_imp > 0 else 0
    total_cpa = (total_spend / total_conv) if total_conv > 0 else 0

    # 広告別行
    ad_rows_html = ""
    for r in rows:
        label_class = ""
        if "勝ち" in r["label"]:
            label_class = "win"
        elif "負け" in r["label"]:
            label_class = "lose"
        elif "データ不足" in r["label"]:
            label_class = "pending"

        ad_rows_html += f"""<tr>
            <td>{r['ad_name']}</td>
            <td>{r['site']}</td>
            <td class="num">{r['impressions']:,}</td>
            <td class="num">{r['ctr']:.2f}%</td>
            <td class="num">¥{r['cpc']:,.0f}</td>
            <td class="num">{r['conversions']}</td>
            <td class="num">{r['purchases']}</td>
            <td class="num">{r['cvr']:.2f}%</td>
            <td class="num">¥{r['cpa']:,.0f}</td>
            <td class="num">¥{r['spend']:,.0f}</td>
            <td class="{label_class}">{r['label']}</td>
        </tr>"""

    # 現状分析
    analysis_html = ""
    for a in analysis:
        body_html = a["body"].replace("\n", "<br>")
        analysis_html += f"""<div class="analysis-item">
            <h3>{a['title']}</h3>
            <p>{body_html}</p>
        </div>"""

    # 改善提案
    suggestion_html = ""
    for s in suggestions:
        pri_class = "pri-high" if s["priority"] == "高" else "pri-mid"
        suggestion_html += f"""<div class="suggestion">
            <div class="suggestion-header">
                <span class="{pri_class}">[{s['priority']}]</span>
                <strong>{s['category']}</strong>
            </div>
            <p class="issue">{s['issue']}</p>
            <p class="action">{s['action']}</p>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Facebook広告レポート {since} 〜 {until}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, "Hiragino Sans", "Meiryo", sans-serif;
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
  tfoot td {{ font-weight: 700; border-top: 2px solid #333; }}
  .win {{ color: #1e8e3e; font-weight: 700; }}
  .lose {{ color: #d93025; font-weight: 700; }}
  .pending {{ color: #f9ab00; }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }}
  .kpi {{ text-align: center; padding: 16px; background: #f8f9fa; border-radius: 8px; }}
  .kpi .value {{ font-size: 28px; font-weight: 700; color: #1a73e8; }}
  .kpi .label {{ font-size: 12px; color: #888; margin-top: 4px; }}
  .suggestion {{ padding: 16px; border-left: 4px solid #1a73e8; margin-bottom: 12px;
                 background: #f8f9fa; border-radius: 0 8px 8px 0; }}
  .suggestion-header {{ margin-bottom: 8px; }}
  .pri-high {{ color: #d93025; font-weight: 700; }}
  .pri-mid {{ color: #f9ab00; font-weight: 700; }}
  .analysis-item {{ padding: 12px 16px; margin-bottom: 10px; background: #f8f9fa;
                    border-radius: 8px; }}
  .analysis-item h3 {{ font-size: 14px; color: #333; margin-bottom: 6px; }}
  .analysis-item p {{ font-size: 13px; color: #555; line-height: 1.6; }}
  .issue {{ color: #555; margin-bottom: 6px; }}
  .action {{ color: #1a73e8; font-size: 13px; }}
  .footer {{ text-align: center; color: #aaa; font-size: 11px; margin-top: 30px; }}
  @media print {{
    body {{ background: #fff; padding: 0; }}
    .section {{ box-shadow: none; border: 1px solid #ddd; }}
  }}
</style>
</head>
<body>
<div class="container">
  <h1>Facebook広告パフォーマンスレポート</h1>
  <p class="period">{since} 〜 {until}</p>

  <div class="kpi-grid">
    <div class="kpi">
      <div class="value">¥{total_spend:,.0f}</div>
      <div class="label">総消化額</div>
    </div>
    <div class="kpi">
      <div class="value">{total_imp:,}</div>
      <div class="label">総インプレッション</div>
    </div>
    <div class="kpi">
      <div class="value">{total_ctr:.2f}%</div>
      <div class="label">平均CTR</div>
    </div>
    <div class="kpi">
      <div class="value">{total_conv}</div>
      <div class="label">総CV数</div>
    </div>
  </div>

  <div class="section">
    <h2>サイト別サマリー</h2>
    <table>
      <thead><tr>
        <th>サイト</th><th class="num">消化額</th><th class="num">IMP</th>
        <th class="num">Click</th><th class="num">CTR</th>
        <th class="num">登録</th><th class="num">課金</th><th class="num">CPA</th>
      </tr></thead>
      <tbody>{site_rows_html}</tbody>
      <tfoot><tr>
        <td>合計</td>
        <td class="num">¥{total_spend:,.0f}</td>
        <td class="num">{total_imp:,}</td>
        <td class="num">{total_clicks:,}</td>
        <td class="num">{total_ctr:.2f}%</td>
        <td class="num">{total_conv}</td>
        <td class="num">{total_purch}</td>
        <td class="num">¥{total_cpa:,.0f}</td>
      </tr></tfoot>
    </table>
  </div>

  <div class="section">
    <h2>広告別パフォーマンス</h2>
    <table>
      <thead><tr>
        <th>広告名</th><th>サイト</th><th class="num">IMP</th>
        <th class="num">CTR</th><th class="num">CPC</th>
        <th class="num">登録</th><th class="num">課金</th><th class="num">CVR</th>
        <th class="num">CPA</th><th class="num">消化額</th><th>判定</th>
      </tr></thead>
      <tbody>{ad_rows_html}</tbody>
    </table>
  </div>

  <div class="section">
    <h2>現状分析</h2>
    {analysis_html}
  </div>

  <div class="section">
    <h2>改善提案</h2>
    {suggestion_html}
  </div>

  <p class="footer">Generated by Facebook Ad Report Tool — {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
</div>
</body>
</html>"""

    with open(filename, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"🌐 HTML: {filename}")
    return filename


def export_pdf(html_path, out_dir):
    """HTMLからPDFを生成（weasyprint使用）"""
    try:
        from weasyprint import HTML as WPHTML
    except ImportError:
        print("⚠️  PDF出力にはweasyprintが必要です: pip install weasyprint")
        return None

    pdf_path = out_dir / html_path.stem.replace("report_", "report_")
    pdf_path = html_path.with_suffix(".pdf")

    WPHTML(filename=str(html_path)).write_pdf(str(pdf_path))
    print(f"📑 PDF: {pdf_path}")
    return pdf_path


def build_notify_message(rows, since, until, suggestions=None):
    """通知用のサマリーメッセージを組み立て"""
    is_daily = (since == until)

    sites = {}
    for r in rows:
        s = r["site"]
        if s not in sites:
            sites[s] = {"spend": 0, "conv": 0, "purch": 0}
        sites[s]["spend"] += r["spend"]
        sites[s]["conv"] += r["conversions"]
        sites[s]["purch"] += r["purchases"]

    total_spend = sum(d["spend"] for d in sites.values())
    total_conv = sum(d["conv"] for d in sites.values())
    total_purch = sum(d["purch"] for d in sites.values())
    avg_cpa = (total_spend / total_conv) if total_conv > 0 else 0

    date_label = since if is_daily else f"{since} 〜 {until}"
    lines = [
        f"📊 Facebook広告レポート",
        f"📅 {date_label}", "",
        f"💰 総消化: ¥{total_spend:,.0f}",
        f"📝 登録: {total_conv}件 / 課金: {total_purch}件",
        f"📈 CPA: ¥{avg_cpa:,.0f}（目標¥{BENCH['cpa']:,}）", "",
    ]

    for site, d in sites.items():
        cpa = (d["spend"] / d["conv"]) if d["conv"] > 0 else 0
        icon = "✅" if cpa <= BENCH["cpa"] else "🔴"
        lines.append(f"{icon} {site}: ¥{d['spend']:,.0f} 登録{d['conv']} 課金{d['purch']} CPA¥{cpa:,.0f}")

    # 週次・月次のみ: 即停止推奨 + 改善提案
    if not is_daily:
        stop_ads = [r for r in rows if r["impressions"] >= 500
                    and ((r["cpa"] > BENCH["cpa"] * 3 and r["purchases"] == 0)
                         or (r["impressions"] >= 1000 and r["conversions"] == 0))]
        if stop_ads:
            lines.append("")
            lines.append(f"🛑 即停止推奨: {len(stop_ads)}本")
            for r in stop_ads[:3]:
                lines.append(f"  ・{r['ad_name']} CPA¥{r['cpa']:,.0f}")

        if suggestions:
            lines.append("")
            lines.append(f"💡 改善提案（{len(suggestions)}件）")
            for s in suggestions:
                lines.append(f"[{s['priority']}] {s['category']}")
                lines.append(f"  {s['action']}")

    return "\n".join(lines)


def send_line_message(rows, since, until, suggestions=None):
    """LINE Messaging APIでレポートサマリーを送信（broadcast: 友だち全員に配信）"""
    channel_token = os.getenv("LINE_CHANNEL_TOKEN")

    if not channel_token:
        print("⚠️  LINE_CHANNEL_TOKEN が未設定。LINE通知をスキップ。")
        return

    msg = build_notify_message(rows, since, until, suggestions=suggestions)

    # broadcast API — 友だち全員に送信（ユーザーID不要）
    payload = json.dumps({
        "messages": [{"type": "text", "text": msg}],
    }).encode()

    req = urllib.request.Request(
        "https://api.line.me/v2/bot/message/broadcast",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {channel_token}",
        },
    )
    try:
        urllib.request.urlopen(req)
        print("📱 LINE通知を送信しました")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"⚠️  LINE通知エラー: {e.code} {body}")
    except Exception as e:
        print(f"⚠️  LINE通知エラー: {e}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Facebook広告レポート生成")
    parser.add_argument("--since", help="開始日 YYYY-MM-DD（デフォルト: 7日前）")
    parser.add_argument("--until", help="終了日 YYYY-MM-DD（デフォルト: 昨日）")
    parser.add_argument("--days", type=int, default=7, help="過去N日間（デフォルト: 7）")
    parser.add_argument("--no-csv", action="store_true", help="CSV出力しない")
    parser.add_argument("--no-html", action="store_true", help="HTML出力しない")
    parser.add_argument("--pdf", action="store_true", help="PDF出力する")
    parser.add_argument("--notify", action="store_true", help="LINE通知を送信")
    parser.add_argument("--out-dir", help="HTML/CSV出力先ディレクトリ")
    args = parser.parse_args()

    today = datetime.date.today()
    if args.since:
        since = args.since
    else:
        since = (today - datetime.timedelta(days=args.days)).isoformat()
    if args.until:
        until = args.until
    else:
        until = (today - datetime.timedelta(days=1)).isoformat()

    print(f"\n📡 Meta API からデータ取得中... ({since} 〜 {until})")

    account = init_api()
    insights = fetch_ad_insights(account, since, until)

    if not insights:
        print("⚠️  該当期間のデータがありません。広告がACTIVEか確認してください。")
        sys.exit(0)

    rows = process_insights(insights)
    analysis = generate_analysis(rows)
    suggestions = generate_suggestions(rows)

    # ターミナル出力
    print_report(rows, analysis, suggestions, since, until)

    # ファイル出力
    out_dir = Path(args.out_dir) if args.out_dir else Path(__file__).parent / "exports"

    if not args.no_csv:
        export_csv(rows, since, until, out_dir)

    html_path = None
    if not args.no_html:
        html_path = export_html(rows, analysis, suggestions, since, until, out_dir)

    if args.pdf and html_path:
        export_pdf(html_path, out_dir)
    elif args.pdf and not html_path:
        html_path = export_html(rows, analysis, suggestions, since, until, out_dir)
        export_pdf(html_path, out_dir)

    # LINE通知
    if args.notify:
        send_line_message(rows, since, until, suggestions=suggestions)

    print("\n✅ レポート生成完了\n")


if __name__ == "__main__":
    main()
