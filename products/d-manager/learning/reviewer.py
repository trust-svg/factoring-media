"""学習レビュアー — 1セッション（チャンネル+日付）の会話を振り返り、.company/ の skill/memory/rules を更新する。

# Adapted from Hermes Agent (MIT) — github.com/NousResearch/hermes-agent
# REVIEWER_PERSONA / REVIEW_PROMPT は Hermes の _COMBINED_REVIEW_PROMPT と "do NOT capture" ブロックリストをベースに移植。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_SUMMARY_RE = re.compile(r"<summary>\s*(\w+)\s*:\s*(.*?)\s*</summary>", re.DOTALL)


def parse_summary(text: str) -> Optional[tuple[str, str]]:
    """出力末尾の <summary>status: note</summary> を (status, note) で返す。無ければ None。"""
    matches = list(_SUMMARY_RE.finditer(text or ""))
    if not matches:
        return None
    m = matches[-1]
    return (m.group(1).strip(), m.group(2).strip())


def format_conversation_log(
    channel_name: str,
    department: str,
    review_date: str,
    turns: list[dict],
    char_limit: int = 40000,
) -> str:
    header = f"## 会話ログ — {channel_name} / {department} / {review_date}\n"
    lines = [f"[{t['role']}] {t['content']}" for t in turns]
    body = "\n".join(lines)
    full = header + body
    if len(full) <= char_limit:
        return full
    # 先頭20% + 末尾60%（末尾＝結論・つまずき解決が出やすい）、中略マーカー
    head_n = int(char_limit * 0.2)
    tail_n = int(char_limit * 0.6)
    head = body[:head_n]
    tail = body[-tail_n:]
    omitted = len(body) - head_n - tail_n
    return f"{header}{head}\n\n（中略 — 約{omitted}文字省略）\n\n{tail}"


REVIEWER_PERSONA = """あなたは TrustLink の学習レビュアーです。12名のAI社員のような人格は持ちません。
1つの会話ログを読み、次回以降の再現性につながる学びだけを `.company/` の所定の場所に書き込む単機能エージェントです。
社訓のうち次の3つを厳守: (1)嘘をつくな・捏造するな (2)古い情報を使い回すな・常に最新を取りに行け (7)学びを記録せよ。
あなたが使える操作はファイルの Read/Write/Edit/Glob/Grep のみです。
メール送信・eBay API・広告API・git push・外部コマンド実行など、ファイル更新以外のことは一切してはいけません。"""


def build_review_prompt(
    conversation_log: str,
    channel_name: str,
    department: str,
    review_date: str,
    recent_learnings: str,
    dryrun: bool,
    extra_context: str = "",
) -> str:
    """レビュー本体プロンプトを組み立てる。`recent_learnings` は直近7日に記録済みの学び一覧（重複防止）。"""
    dryrun_note = (
        "\n\n【ドライランモード】ファイルは一切書くな（Write/Edit するな）。"
        "もし本番なら何をどこに書くつもりだったかを <summary> に詳細に列挙せよ。"
        if dryrun
        else ""
    )
    return f"""以下は {channel_name}（部門: {department}）で {review_date} に交わされた会話ログです。
ここから「次回以降の再現性につながる学び」だけを抽出し、`.company/` の適切な場所を更新してください。
学びが無ければ何もせず、最後に `<summary>no_learnings: 理由</summary>` だけ返してください。{dryrun_note}

## 書き込み先の振り分け
- 再現性のある手順（「Xをやるときはこの順で」）→ `.company/skills/<name>.md`（既存スキルに追記できるなら新規作成せず Edit を優先。スキル本文が概ね80-100行を超えそうなら、骨子だけ `<name>/SKILL.md` に残し、詳細・長いサンプル・チェックリストは `<name>/references/*.md` に分けて作る）。frontmatter は `name` / `owner` / `trigger`。
- 確定した事実（「クライアントAの請求書は月末締め」など）→ `.company/secretary/memory/facts/<topic>.md`（1行ずつ。同じ趣旨が既にあれば追記しない。宣言形で書く＝「〜である」、「〜せよ」ではない）。
- 振り返り知見（「この施策はこういう理由で効いた」）→ `.company/secretary/memory/digest/<topic>.md`（`## {review_date}` の見出しの下に書く）。
- 「2回以上同じ指摘を受けた」級の運用ルール → `.company/secretary/rules.md`（既存の追記フォーマットに合わせる）。
- 部門固有の業務知識 → `.company/{department}/knowledge/<topic>.md`（500行を超えそうなら分割）。

## 保存してはいけないもの（重要）
- 環境依存の失敗（APIキー切れ・ネット断・特定マシン固有の事象）。これを「〜は使えない」という恒久ルールに固めるな。
- ツールへの否定的主張（「Xは動かない」を恒久ルール化しない）。
- 一過性のエラー・リトライで直ったもの。
- 一回限りのタスクの語り（「今日Aさんに返信した」自体は記録不要。そこから学んだ"やり方"だけ）。
- 既に `.company/skills/` や `.company/secretary/rules.md` に書いてあること（重複）。事前に Grep で確認すること。
- 新しい狭いスキルを作るより、既存の包括スキルにパッチを当てる方を常に優先せよ。

## 既に記録済みの学び（重複チェック用・抜粋）
{recent_learnings or "(なし)"}

{extra_context}

## 会話ログ
{conversation_log}

---
作業が終わったら、必ず最後に1つだけ `<summary>` ブロックを返してください。
- 何か書いた場合: `<summary>done: 何をどこに書いたか（ファイルパスと一言）</summary>`
- 学びが無かった場合: `<summary>no_learnings: 理由</summary>`
"""
