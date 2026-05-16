#!/usr/bin/env python3
"""
#5 ロングテールKW新規記事生成
低競争・高コンバージョン意図のKWで新記事を自動生成する

使い方:
  venv/bin/python generate_articles.py --preview   # 記事一覧と対象KW確認
  venv/bin/python generate_articles.py --all        # 全記事生成・保存
"""

import argparse
import os
import sys
from datetime import date
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

ARTICLES_DIR = Path(__file__).parent.parent / "content/articles"
client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
TODAY = date.today().isoformat()

# 新規記事スペック
NEW_ARTICLES = [
    {
        "slug": "manufacturing-factoring",
        "title": "製造業のファクタリング比較おすすめ｜下請け・中小メーカーの資金繰りを即日改善",
        "description": "製造業の資金繰りを即日改善するファクタリング業者を比較。支払いサイト90〜120日・原材料先払いの二重苦を解決する手数料2〜12%の業者選びと、審査が通りやすいコツを解説。",
        "category": "業種別",
        "keywords": [
            "ファクタリング 製造業",
            "製造業 資金繰り",
            "下請け 製造業 ファクタリング",
            "メーカー ファクタリング",
        ],
        "target": "製造業の経営者・財務担当者。売掛先が大手メーカー・商社の下請け企業が多い。支払いサイトが長く（90〜120日）、原材料の先払いが必要な業種。",
        "key_points": [
            "製造業の資金繰りが厳しい理由（支払いサイト長い・原材料先払い・季節変動）",
            "製造業に向いているファクタリング業者の選び方（大口対応・3社間の使い方）",
            "業者比較表（ビートレーディング・アクセルファクター・アウル経済・ベストファクター）",
            "下請け製造業のケーススタディ（売掛金500万円・支払いサイト120日のシミュレーション）",
            "FAQセクション（赤字決算でも使える？元請けに知られない？）",
        ],
    },
    {
        "slug": "restaurant-factoring",
        "title": "飲食業のファクタリング｜食材仕入れ・家賃資金を即日調達する方法と注意点",
        "description": "飲食業の急な資金不足を解決するファクタリングの使い方。食材仕入れ・家賃・人件費の支払いに間に合う即日入金業者の選び方、飲食業特有の審査ポイントと手数料の相場を解説。",
        "category": "業種別",
        "keywords": [
            "ファクタリング 飲食業",
            "飲食店 資金繰り",
            "飲食業 即日 融資",
            "飲食店 資金調達",
        ],
        "target": "飲食店経営者（個人・法人）。B2Cが多く売掛金が少ない業種だが、チェーン店・法人相手の給食・ケータリング・食品製造では売掛金が発生する。",
        "key_points": [
            "飲食業でファクタリングが使えるケースと使えないケースの明確な区分",
            "給食・ケータリング・食品製造は売掛金あり→ファクタリング可能",
            "B2C飲食店は売掛金なし→クレジットカード前払いサービスや事業者ローンとの比較",
            "飲食業に強いファクタリング業者（少額対応・個人事業主対応）",
            "FAQセクション（個人事業主の居酒屋でも使える？キャッシュレス売上は対象？）",
        ],
    },
    {
        "slug": "factoring-no-guarantor",
        "title": "保証人なし・担保なしで使えるファクタリング｜銀行融資と何が違う？",
        "description": "ファクタリングは保証人・担保が不要な資金調達手段。銀行融資との根本的な違い、保証人なしで使える業者5選、無担保でも審査が通る条件と注意点を徹底解説。",
        "category": "基礎知識",
        "keywords": [
            "ファクタリング 保証人なし",
            "ファクタリング 担保なし",
            "ファクタリング 無担保",
            "保証人不要 資金調達",
        ],
        "target": "銀行融資で保証人・担保を求められて断られた中小企業・個人事業主。「保証人なし」「担保なし」で検索する層はファクタリングを知らないことも多い。",
        "key_points": [
            "なぜファクタリングは保証人・担保が不要なのか（仕組みの説明）",
            "銀行融資 vs ファクタリングの比較表（保証人・担保・審査期間・コスト）",
            "保証人なしで使える業者5社の比較（ビートレーディング・アクセルファクター・ペイトナー等）",
            "注意点：保証人不要でも審査はある（売掛先の信用力が重要）",
            "FAQセクション（信用情報がブラックでも使える？個人事業主でも保証人不要？）",
        ],
    },
    {
        "slug": "agriculture-factoring",
        "title": "農業のファクタリング｜農協・食品メーカーへの売掛金を即日資金化する方法",
        "description": "農業・農家の売掛金（農協・食品メーカー）をファクタリングで即日資金化する方法。農業特有の季節性資金需要・収穫前の資金不足を解決する業者の選び方と手数料の実態を解説。",
        "category": "業種別",
        "keywords": [
            "ファクタリング 農業",
            "農家 資金繰り",
            "農協 売掛金 資金化",
            "農業 即日 資金調達",
        ],
        "target": "農業法人・大規模農家。農協・食品メーカー・スーパーへの卸売で売掛金が発生する。収穫期と入金時期のズレ、農機具・農薬の先払いが課題。",
        "key_points": [
            "農業でファクタリングが使えるケース（農協・食品メーカー・スーパーへの卸）",
            "農業の資金繰りが厳しい構造的理由（収穫→出荷→入金の3〜6ヶ月ギャップ）",
            "農業に対応できる業者の選び方（農業に理解のある担当者がいるか）",
            "農業法人 vs 個人農家：どちらが審査が通りやすいか",
            "農業政策金融公庫との使い分け",
        ],
    },
    {
        "slug": "factoring-tax-arrears",
        "title": "税金滞納でもファクタリングは使える？審査への影響と利用できる業者",
        "description": "税金滞納中でもファクタリングを利用できる理由と条件を解説。国税・地方税の滞納が審査に与える影響、差押えリスクとの関係、滞納中でも対応してくれる業者の選び方。",
        "category": "注意点",
        "keywords": [
            "ファクタリング 税金滞納",
            "税金滞納 資金調達",
            "滞納 ファクタリング 審査",
            "国税 滞納 ファクタリング",
        ],
        "target": "資金繰り悪化により納税が遅れている事業者。銀行融資は絶望的と考えている層。「税金滞納 ファクタリング」で検索するのは切迫度が高いユーザー。",
        "key_points": [
            "税金滞納でもファクタリングが使える理由（審査は売掛先の信用力が基準）",
            "税金滞納が審査に影響する部分としない部分",
            "差押えリスク：税務署が売掛金を差押えるケースとファクタリングの関係",
            "滞納中でも対応してくれる業者の特徴（2社間中心・オンライン系）",
            "ファクタリングで得た資金を滞納解消に使うことの是非",
            "FAQセクション（差押え中でも使える？税務署にバレる？）",
        ],
    },
]


ARTICLE_PROMPT = """あなたはファクタリング（売掛金の早期現金化）の専門メディア「FACCEL」の編集者です。
以下の仕様でSEO記事を作成してください。

【記事仕様】
タイトル: {title}
ターゲット読者: {target}
記事に含める要素:
{key_points}

【執筆ルール】
- frontmatterは出力しない（別途設定する）
- ## 見出し、### 小見出しで構成（H1は使わない）
- 冒頭2〜3文でユーザーの課題に共感する書き出し
- 比較表がある場合はマークダウンテーブル形式
- よくある質問（FAQ）セクションを最後に5問（Q:/A:形式）
- 締めは「無料診断はこちら」CTA（[無料診断はこちら](/estimate)）
- 文字数目安: 1,500〜2,000字
- 事実に基づく具体的な数字を入れる（手数料○%、入金○時間、など）
- 過度な誇大表現・断定的表現を避ける中立的なトーン

記事本文を出力してください（frontmatterなし）:"""


def generate_article_body(spec: dict) -> str:
    key_points_str = "\n".join(f"- {p}" for p in spec["key_points"])
    prompt = ARTICLE_PROMPT.format(
        title=spec["title"],
        target=spec["target"],
        key_points=key_points_str,
    )
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2500,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip()


def build_article(spec: dict, body: str) -> str:
    keywords_str = '", "'.join(spec["keywords"])
    frontmatter = f'''---
title: "{spec["title"]}"
description: "{spec["description"]}"
date: "{TODAY}"
category: "{spec["category"]}"
author: "ファクセル編集部"
keywords: ["{keywords_str}"]
---

'''
    footer = """
---

**📌 おすすめファクタリング業者**

[アウル経済のファクタリング](https://faccel.jp/go/owl-keizai) — 中小企業特化・手数料1〜10%・最短即日・担保/保証人不要。

[ペイトナー ファクタリング](https://faccel.jp/go/paytner) — 最短10分で入金・請求書1枚からOK・オンライン完結。

※PR（アフィリエイト広告を含みます）
"""
    return frontmatter + body + footer


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    if not args.preview and not args.all:
        parser.print_help()
        sys.exit(1)

    if args.preview:
        print(f"生成予定: {len(NEW_ARTICLES)}記事\n")
        for a in NEW_ARTICLES:
            exists = (ARTICLES_DIR / f"{a['slug']}.md").exists()
            status = "⚠️ 既存ファイルあり（上書き）" if exists else "✅ 新規"
            print(f"  {status} {a['slug']}")
            print(f"    KW: {', '.join(a['keywords'][:2])}")
        return

    for i, spec in enumerate(NEW_ARTICLES, 1):
        path = ARTICLES_DIR / f"{spec['slug']}.md"
        print(f"[{i}/{len(NEW_ARTICLES)}] {spec['slug']} を生成中...")
        body = generate_article_body(spec)
        article = build_article(spec, body)
        path.write_text(article, encoding="utf-8")
        print(f"  → 保存: {path.name} ({len(article)}字)")

    print(f"\n✅ {len(NEW_ARTICLES)}記事を生成しました。")


if __name__ == "__main__":
    main()
