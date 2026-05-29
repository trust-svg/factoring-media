---
name: skill-quality-checker
description: Use after creating or editing any skill (SKILL.md) to verify it meets cross-tool quality standards before committing. Checks frontmatter, trigger description, body length, I/O clarity, resource separation, MCP independence, single-responsibility, and source trust.
---

# Skill Quality Checker

新規スキルの作成・編集が終わったら、コミット前にこの8項目で自己採点する。Claude Code / Codex 両方で使える共通スキルの品質ゲート。各項目 PASS/FAIL を出し、FAIL があれば直してから完了報告する。

## いつ使うか

- `_shared-ai/skills/` または `~/.claude/skills/`・`~/.codex/skills/` に新スキルを作った直後
- 既存スキルの description や本文を大きく書き換えた後
- `/skill-creator` の出力を共通領域へ昇格させる前

## チェック8項目

1. **frontmatter 完備** — `name`（kebab-case・ディレクトリ名と一致）と `description` が両方ある。共通スキルは余計なキーを足さない（Codex は name/description のみ読む）。
2. **description が自然言語トリガー** — 「いつ使うか」が三人称・具体動詞で書かれている（"Use when…", "Use after…"）。単なる機能名の言い換えは FAIL。トリガー語が曖昧だと自動発火しない。
3. **本文の分量** — 概ね 1,500〜3,000 字。短すぎ＝手順不足、長すぎ＝progressive disclosure 違反。詳細手順や長い表は `references/` へ逃がす。
4. **入力と出力が明示** — 「何を受け取り何を返すか」が読めば分かる。前提ファイル・必要な引数・成果物の形式を本文冒頭で宣言。
5. **補助データの分離** — テンプレート・チェックリスト・サンプルは `references/` や `assets/` に置き、SKILL.md 本文からは参照のみ。本文に大量データを埋めない。
6. **MCP 非依存（または依存を明記）** — 特定 MCP サーバが無いと動かない手順は避ける。やむを得ず依存するなら本文に「要 MCP: xxx」と明記し、CLI 代替があれば併記。
7. **1スキル1責任** — やることが1つに絞られている。「Xを監査し、ついでにYも生成しBにも通知」のような多責任は分割。
8. **信頼ソース** — 外部事実・数値・仕様を載せるなら出典 or 取得方法を残す。古びる情報はハードコードせず取得手順を書く。

## 出力形式

```
skill-quality-checker: <skill-name>
1. frontmatter完備      [PASS/FAIL] 一言
2. descriptionトリガー   [PASS/FAIL] 一言
3. 本文分量(xxxx字)      [PASS/FAIL] 一言
4. I/O明示              [PASS/FAIL] 一言
5. 補助データ分離        [PASS/FAIL] 一言
6. MCP非依存            [PASS/FAIL] 一言
7. 1スキル1責任         [PASS/FAIL] 一言
8. 信頼ソース           [PASS/FAIL] 一言
総合: PASS / 要修正(n項目)
```

FAIL があれば該当ファイルを直してから再チェック。全 PASS になるまで「完了」と報告しない。
