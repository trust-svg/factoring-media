#!/usr/bin/env python3
"""
faccel.jp 記事自動生成スクリプト
GitHub Actions (Mon/Wed/Fri 9:07 JST) から実行される。
未執筆の優先記事を1本生成して content/articles/ に書き出す。
"""

import json
import os
import sys
from datetime import date
from pathlib import Path
import anthropic

# seed.ts上のcompanySlugと対応するレビュー記事スラグのマッピング
# 優先度順（上から執筆）
REVIEW_PRIORITY = [
    ("beat-trading",    "beat-trading-review"),
    ("factoru",         "factoru-review"),
    ("jfc-support",     "jfc-support-review"),
    ("olta",            "olta-review"),
    ("paytoday",        "paytoday-review"),
    ("labol",           "labol-review"),
    ("top-management",  "top-management-review"),
    ("ennavi",          "ennavi-review"),
]

# レビュー以外の知識系記事（優先度順）
KNOWLEDGE_PRIORITY = [
    ("factoring-cannot-repay",      "ファクタリングで返済できない場合はどうなる？リスクと対処法を解説"),
    ("factoring-double-assignment", "売掛債権の二重譲渡とは？ファクタリングでのリスクと防止策"),
    ("factoring-scam-detection",    "ファクタリング詐欺・悪質業者の見分け方と被害を防ぐチェックリスト"),
    ("salary-factoring-illegal",    "給与ファクタリングはなぜ違法？仕組みと合法サービスとの違い"),
    ("factoring-rejected-reason",   "ファクタリング審査に落ちる理由と通過率を上げる対策"),
]

ARTICLES_DIR = Path("content/articles")
SEED_FILE = Path("prisma/seed.ts")
NOTE_SCHEDULE_FILE = Path("content/note-schedule.json")
REFERENCE_REVIEW = ARTICLES_DIR / "pmg-review.md"
REFERENCE_KNOWLEDGE = ARTICLES_DIR / "factoring-illegal.md"


def get_existing_slugs() -> set[str]:
    return {f.stem for f in ARTICLES_DIR.glob("*.md")}


def get_note_intel() -> dict[str, dict]:
    """
    note側の執筆状況を返す。key=slug, value={status, note_url, date}
    ファイルが無ければ空dict。GitHub Actions でもローカルでも動作する。
    """
    if not NOTE_SCHEDULE_FILE.exists():
        return {}
    try:
        data = json.loads(NOTE_SCHEDULE_FILE.read_text(encoding="utf-8"))
        return {
            entry["slug"]: {
                "status": entry.get("status"),
                "note_url": entry.get("note_url"),
                "date": entry.get("date"),
            }
            for entry in data.get("queue", [])
        }
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Warning: note-schedule.json parse error: {e}", file=sys.stderr)
        return {}


def find_next_target(existing: set[str]) -> tuple[str, str, bool] | None:
    """
    Returns (company_slug_or_None, article_slug, is_review)
    or None if nothing to do.
    """
    for company_slug, article_slug in REVIEW_PRIORITY:
        if article_slug not in existing:
            return company_slug, article_slug, True

    for article_slug, _ in KNOWLEDGE_PRIORITY:
        if article_slug not in existing:
            return None, article_slug, False

    return None


def format_note_context(article_slug: str, note_intel: dict[str, dict]) -> str:
    """
    note側の同スラッグ情報をプロンプトに埋め込むテキストに整形。
    同じスラッグが note にあれば差別化を促す指示を返す。
    """
    note_entry = note_intel.get(article_slug)
    if not note_entry:
        return ""

    status = note_entry.get("status")
    note_url = note_entry.get("note_url")
    note_date = note_entry.get("date")

    lines = ["## note側の執筆・公開状況（重要・必ず確認）", ""]
    if status == "published" and note_url:
        lines.append(
            f"同じスラッグ `{article_slug}` で note.com にも記事が公開されています: {note_url}"
        )
        lines.append(
            "**note版と完全に同じ文章にはせず、切り口・構成・具体例を変えて差別化してください。**"
        )
        lines.append(
            "ただし、事実（手数料・審査基準等）は同じものを使ってください。評価や論点の立て方を変える方向で。"
        )
    elif status == "scheduled":
        lines.append(
            f"同じスラッグ `{article_slug}` は note.com でも執筆予定です（予定日: {note_date}）。"
        )
        lines.append(
            "**note版と内容が完全に重複しないよう、この記事はウェブ検索流入（SEO）重視で書いてください。**"
        )
        lines.append(
            "note版は読み物・体験ベース寄りで書かれる前提です。こちらはFAQ・比較表・構造化データ等の情報網羅性で差別化を。"
        )
    else:
        return ""

    return "\n".join(lines) + "\n"


def get_knowledge_theme(article_slug: str) -> str:
    for slug, theme in KNOWLEDGE_PRIORITY:
        if slug == article_slug:
            return theme
    return article_slug


def generate_review(company_slug: str, article_slug: str, note_context: str) -> str:
    seed_content = SEED_FILE.read_text()
    reference = REFERENCE_REVIEW.read_text()
    today = date.today().strftime("%Y-%m-%d")

    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": f"""ファクタリング情報メディア「ファクセル（faccel.jp）」向けに、業者レビュー記事を1本執筆してください。

## 対象
- companySlug（seed.ts内のキー）: {company_slug}
- 出力ファイルスラグ: {article_slug}

{note_context}
## seed.ts（会社データ・口コミが含まれる）
以下のファイルから {company_slug} に関するデータを使用してください。

```
{seed_content}
```

## 参考フォーマット（この構成・文体・長さに合わせる）
```
{reference}
```

## 執筆条件
- date: {today}
- frontmatter の slug: {article_slug}
- category: "業者レビュー"
- author: "ファクセル編集部"
- keywords: 検索ボリュームがありそうな日本語キーワード5つ
- 文字数: 2,000字以上
- 口コミは seed.ts の body を実際の声として引用する
- 中立的・客観的な論調（過度な主観・断定を避ける）
- 末尾に必ず `[ファクセル](https://faccel.jp)` リンクを含める

frontmatter（---〜---）から本文末尾まで、完全なMarkdown記事を出力してください。
コードブロック（```）で囲まないでください。"""
        }]
    )
    return message.content[0].text.strip()


def generate_knowledge(article_slug: str, note_context: str) -> str:
    theme = get_knowledge_theme(article_slug)
    reference = REFERENCE_KNOWLEDGE.read_text()
    today = date.today().strftime("%Y-%m-%d")

    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": f"""ファクタリング情報メディア「ファクセル（faccel.jp）」向けに、知識系SEO記事を1本執筆してください。

## テーマ
{theme}

## 対象スラグ
{article_slug}

{note_context}
## 参考フォーマット（この構成・文体・長さに合わせる）
```
{reference}
```

## 執筆条件
- date: {today}
- frontmatter の slug: {article_slug}
- category: "基礎知識"
- author: "ファクセル編集部"
- keywords: 検索ボリュームがありそうな日本語キーワード5つ
- 文字数: 2,000字以上
- 読者: ファクタリングを初めて検討している中小企業経営者・個人事業主
- 末尾に必ず `[ファクセル](https://faccel.jp)` リンクを含める

frontmatter（---〜---）から本文末尾まで、完全なMarkdown記事を出力してください。
コードブロック（```）で囲まないでください。"""
        }]
    )
    return message.content[0].text.strip()


def main():
    existing = get_existing_slugs()
    note_intel = get_note_intel()
    target = find_next_target(existing)

    if target is None:
        print("All priority articles already exist. Nothing to do.")
        sys.exit(0)

    company_slug, article_slug, is_review = target
    note_context = format_note_context(article_slug, note_intel)
    has_note = article_slug in note_intel
    print(f"Generating: {article_slug} (review={is_review}, note_aware={has_note})")

    if is_review:
        content = generate_review(company_slug, article_slug, note_context)
    else:
        content = generate_knowledge(article_slug, note_context)

    output_path = ARTICLES_DIR / f"{article_slug}.md"
    output_path.write_text(content, encoding="utf-8")
    print(f"Written: {output_path}")


if __name__ == "__main__":
    main()
