#!/usr/bin/env python3
"""
FACCEL 記事のmeta descriptionをCTR最適化版に書き直す。

使い方:
  venv/bin/python rewrite_descriptions.py --preview 5   # 最初の5件をプレビュー
  venv/bin/python rewrite_descriptions.py --all         # 全件書き換え
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


def rewrite_description(
    title: str, description: str, category: str, keywords: list[str]
) -> str:
    kw_str = "、".join(keywords[:3]) if keywords else ""
    prompt = f"""ファクタリング情報メディア「FACCEL」の記事のmeta descriptionを書き直してください。

【記事情報】
タイトル: {title}
カテゴリ: {category}
主要KW: {kw_str}
現在のdescription: {description}

【書き直しルール】
- 文字数: 110〜140字（Googleの表示上限）
- ユーザーの疑問に直接答える書き出しにする
- 具体的な数字・データを1つ以上含める（例: 手数料5〜14.8%、即日対応可能、3社比較など）
- 「〜を解説します」「〜について紹介します」などの締め方NG → 得られる具体的なメリットで締める
- 読んで得られるベネフィットが明確に伝わること
- descriptionの文字列のみ出力すること（説明文・鍵括弧不要）

出力:"""

    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip().strip("「」")


def parse_frontmatter(text: str) -> dict:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).splitlines():
        if ": " in line:
            k, v = line.split(": ", 1)
            fm[k.strip()] = v.strip().strip('"')
    # keywords list
    kw_m = re.search(r"keywords:\s*\[(.*?)\]", m.group(1))
    if kw_m:
        fm["keywords"] = [k.strip().strip('"') for k in kw_m.group(1).split(",")]
    return fm


def update_description(path: Path, new_desc: str) -> None:
    text = path.read_text(encoding="utf-8")
    updated = re.sub(
        r'^description: ".*?"',
        f'description: "{new_desc}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    path.write_text(updated, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--preview", type=int, metavar="N", help="最初のN件をプレビュー"
    )
    parser.add_argument("--all", action="store_true", help="全件書き換え")
    args = parser.parse_args()

    if not args.preview and not args.all:
        parser.print_help()
        sys.exit(1)

    articles = sorted(ARTICLES_DIR.glob("*.md"))
    if args.preview:
        articles = articles[: args.preview]

    for i, path in enumerate(articles, 1):
        text = path.read_text(encoding="utf-8")
        fm = parse_frontmatter(text)
        if not fm.get("title") or not fm.get("description"):
            continue

        title = fm["title"]
        description = fm["description"]
        category = fm.get("category", "")
        keywords = fm.get("keywords", [])

        new_desc = rewrite_description(title, description, category, keywords)

        print(f"\n[{i}/{len(articles)}] {path.name}")
        print(f"  Before ({len(description)}字): {description}")
        print(f"  After  ({len(new_desc)}字): {new_desc}")

        if args.all:
            update_description(path, new_desc)
            time.sleep(0.3)  # API rate limit

    if args.all:
        print(f"\n✅ {len(articles)}件のdescriptionを書き換えました。")


if __name__ == "__main__":
    main()
