#!/usr/bin/env python3
"""
#2 E-E-A-T強化 + #4 内部リンク整備
- 全業者レビュー記事にFAQセクションを追加
- 業種別ガイド記事への内部リンクを追加

使い方:
  venv/bin/python enhance_reviews.py --preview 3   # 最初の3件をプレビュー
  venv/bin/python enhance_reviews.py --all         # 全件適用
"""

import argparse
import os
import re
import sys
import time
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

ARTICLES_DIR = Path(__file__).parent.parent / "content/articles"
client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# 業者名 → 関連業種記事のマッピング
RELATED_ARTICLES = {
    "beat-trading-review": [
        (
            "/articles/construction-factoring",
            "建設業・下請けのファクタリング活用ガイド",
        ),
        ("/articles/medical-factoring", "診療報酬・介護報酬ファクタリング完全ガイド"),
        (
            "/articles/two-vs-three-factoring",
            "2社間・3社間ファクタリングの違いと選び方",
        ),
    ],
    "betrading-review": [
        (
            "/articles/construction-factoring",
            "建設業・下請けのファクタリング活用ガイド",
        ),
        (
            "/articles/two-vs-three-factoring",
            "2社間・3社間ファクタリングの違いと選び方",
        ),
        ("/articles/factoring-high-fee", "ファクタリング手数料の相場と交渉術"),
    ],
    "axel-factor-review": [
        ("/articles/same-day-factoring", "即日ファクタリング対応業者の選び方"),
        (
            "/articles/construction-factoring",
            "建設業・下請けのファクタリング活用ガイド",
        ),
        (
            "/articles/sole-proprietor-factoring",
            "個人事業主・フリーランスのファクタリング",
        ),
    ],
    "paytner-review": [
        (
            "/articles/sole-proprietor-factoring",
            "個人事業主・フリーランスのファクタリング",
        ),
        ("/articles/small-amount-factoring", "少額ファクタリング（10万円〜）対応業者"),
        ("/articles/online-factoring", "オンライン完結ファクタリングおすすめ"),
    ],
    "olta-review": [
        ("/articles/online-factoring", "オンライン完結ファクタリングおすすめ"),
        ("/articles/easy-approval-factoring", "審査が通りやすいファクタリング業者"),
        (
            "/articles/two-vs-three-factoring",
            "2社間・3社間ファクタリングの違いと選び方",
        ),
    ],
    "labol-review": [
        (
            "/articles/sole-proprietor-factoring",
            "個人事業主・フリーランスのファクタリング",
        ),
        ("/articles/small-amount-factoring", "少額ファクタリング（10万円〜）対応業者"),
        ("/articles/online-factoring", "オンライン完結ファクタリングおすすめ"),
    ],
    "nihon-chuushou-review": [
        (
            "/articles/construction-factoring",
            "建設業・下請けのファクタリング活用ガイド",
        ),
        ("/articles/same-day-factoring", "即日ファクタリング対応業者の選び方"),
        ("/articles/factoring-high-fee", "ファクタリング手数料の相場と交渉術"),
    ],
    "owl-keizai-review": [
        (
            "/articles/construction-factoring",
            "建設業・下請けのファクタリング活用ガイド",
        ),
        ("/articles/medical-factoring", "診療報酬・介護報酬ファクタリング完全ガイド"),
        ("/articles/factoring-high-fee", "ファクタリング手数料の相場と交渉術"),
    ],
    "pmg-review": [
        ("/articles/same-day-factoring", "即日ファクタリング対応業者の選び方"),
        ("/articles/online-factoring", "オンライン完結ファクタリングおすすめ"),
        (
            "/articles/sole-proprietor-factoring",
            "個人事業主・フリーランスのファクタリング",
        ),
    ],
    "best-factor-review": [
        ("/articles/easy-approval-factoring", "審査が通りやすいファクタリング業者"),
        (
            "/articles/construction-factoring",
            "建設業・下請けのファクタリング活用ガイド",
        ),
        ("/articles/factoring-high-fee", "ファクタリング手数料の相場と交渉術"),
    ],
    "factoring-best-review": [
        ("/articles/how-to-choose", "失敗しないファクタリング業者の選び方"),
        ("/articles/factoring-high-fee", "ファクタリング手数料の相場と交渉術"),
        ("/articles/easy-approval-factoring", "審査が通りやすいファクタリング業者"),
    ],
    "ennavi-review": [
        ("/articles/same-day-factoring", "即日ファクタリング対応業者の選び方"),
        ("/articles/online-factoring", "オンライン完結ファクタリングおすすめ"),
        (
            "/articles/sole-proprietor-factoring",
            "個人事業主・フリーランスのファクタリング",
        ),
    ],
    "mentor-capital-review": [
        (
            "/articles/construction-factoring",
            "建設業・下請けのファクタリング活用ガイド",
        ),
        ("/articles/small-amount-factoring", "少額ファクタリング（10万円〜）対応業者"),
        ("/articles/easy-approval-factoring", "審査が通りやすいファクタリング業者"),
    ],
    "jigyou-shikin-agent-review": [
        (
            "/articles/construction-factoring",
            "建設業・下請けのファクタリング活用ガイド",
        ),
        ("/articles/same-day-factoring", "即日ファクタリング対応業者の選び方"),
        (
            "/articles/two-vs-three-factoring",
            "2社間・3社間ファクタリングの違いと選び方",
        ),
    ],
    "top-management-review": [
        (
            "/articles/construction-factoring",
            "建設業・下請けのファクタリング活用ガイド",
        ),
        ("/articles/same-day-factoring", "即日ファクタリング対応業者の選び方"),
        ("/articles/factoring-high-fee", "ファクタリング手数料の相場と交渉術"),
    ],
}

DEFAULT_RELATED = [
    ("/articles/how-to-choose", "失敗しないファクタリング業者の選び方"),
    ("/articles/factoring-high-fee", "ファクタリング手数料の相場と交渉術"),
    ("/articles/what-is-factoring", "ファクタリングとは？仕組みと基礎知識"),
]


def parse_frontmatter(text: str) -> dict:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).splitlines():
        if ": " in line:
            k, v = line.split(": ", 1)
            fm[k.strip()] = v.strip().strip('"')
    return fm


def already_has_faq(text: str) -> bool:
    return bool(re.search(r"よくある質問|FAQ|^Q\.", text, re.MULTILINE))


def generate_faq(title: str, body: str) -> str:
    # 本文から重要部分を抜粋（トークン節約）
    snippet = body[:2000]
    prompt = f"""以下はファクタリング業者の紹介記事です。この記事の業者について、ユーザーがGoogleで実際に検索しそうな疑問をもとにFAQを5問作成してください。

【記事タイトル】{title}

【記事の抜粋】
{snippet}

【FAQ作成ルール】
- Q: と A: の形式で5問
- 質問はユーザーが実際に検索するリアルな疑問（個人事業主でも使える？審査落ちたらどうする？など）
- 回答は2〜4文で具体的に
- 「## よくある質問（FAQ）」という見出しから始める
- マークダウン形式で出力

出力:"""

    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    return "\n\n" + msg.content[0].text.strip()


def build_related_links(slug: str) -> str:
    links = RELATED_ARTICLES.get(slug, DEFAULT_RELATED)
    lines = ["\n\n## 関連記事"]
    for path, label in links:
        lines.append(f"- [{label}]({path})")
    return "\n".join(lines)


def enhance_article(path: Path, preview: bool = False) -> str:
    text = path.read_text(encoding="utf-8")
    fm = parse_frontmatter(text)
    title = fm.get("title", path.stem)
    slug = path.stem

    additions = []
    notes = []

    # FAQ追加
    if not already_has_faq(text):
        faq = generate_faq(title, text)
        additions.append(faq)
        notes.append("FAQ追加")
    else:
        notes.append("FAQ:スキップ（既存）")

    # 内部リンク追加（まとめの前に挿入）
    if "## 関連記事" not in text:
        related = build_related_links(slug)
        additions.append(related)
        notes.append("関連記事リンク追加")
    else:
        notes.append("関連記事:スキップ（既存）")

    summary = ", ".join(notes)

    if not additions:
        return f"  → スキップ（変更なし）"

    if not preview:
        # まとめセクションの直前に挿入
        insert_point = text.rfind("\n## まとめ")
        if insert_point == -1:
            insert_point = text.rfind("\n---\n\n**📌")
        if insert_point == -1:
            insert_point = len(text)

        new_text = text[:insert_point] + "".join(additions) + text[insert_point:]
        path.write_text(new_text, encoding="utf-8")

    return f"  → {summary}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", type=int, metavar="N")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    if not args.preview and not args.all:
        parser.print_help()
        sys.exit(1)

    # レビュー記事のみ対象
    articles = sorted(ARTICLES_DIR.glob("*-review.md"))
    if args.preview:
        articles = articles[: args.preview]

    for i, path in enumerate(articles, 1):
        print(f"[{i}/{len(articles)}] {path.name}")
        result = enhance_article(path, preview=bool(args.preview))
        print(result)
        if not args.preview:
            time.sleep(0.5)

    if args.all:
        print(f"\n✅ {len(articles)}件の業者レビュー記事を更新しました。")


if __name__ == "__main__":
    main()
