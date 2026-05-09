# Workspace Subagents — Quality Gate Pattern

ここはWorkspace直下の Claude Code subagent 群（`.md` で定義）。
コンテンツ系（FACCEL note / saimu-media Threads / YouTube台本 / クライアント納品物）の公開前に、以下の3層を組み合わせて使う。

## 品質ゲートの3層（使い分け）

| ゲート | 種類 | 対象 | 出力 | 起動方法 |
|---|---|---|---|---|
| **content-ops** (`expert-panel`) | installed skill (`~/.claude/skills/content-ops/`) | 完成コンテンツの総合スコア | 7-10名Expert Panelで90+目標、3周まで自動改善 | `/expert-panel` または「panel this」「score this」 |
| **anti-ai-slop** | `.claude/agents/anti-ai-slop.md` | 行単位のAIっぽさ・冗長性 | Critical/Warning/Info の3段階指摘 | `Agent({subagent_type: "anti-ai-slop", ...})` |
| **brand-voice** | `.claude/agents/brand-voice.md` | プロダクト別ブランド整合 | ガイドとの差分指摘 | `Agent({subagent_type: "brand-voice", ...})` |

### 使い分けの目安
- **構造が固まったあと**の総合品質 → `expert-panel`（重い・遅い・高品質）
- **下書きの推敲フェーズ** → `anti-ai-slop`（行レベル軽量）
- **新規プロダクト or 別人が書いた原稿** → `brand-voice`（最初に必ず通す）

## 並列起動パターン（推奨）

公開直前の最終チェックは、**3層を1メッセージ内で並列起動**すると速い。
（参考: `dispatching-parallel-agents` パターン — 独立した読み取り専用エージェントは依存関係がないので同時実行できる）

例（FACCEL note記事公開前の最終ゲート）:
```
1メッセージ内で3つの Agent ツール呼び出しを並列発火:
  - Agent(brand-voice, "products/factoring-media/output/2026-05-09_xxx.md をFACCELガイドで確認")
  - Agent(anti-ai-slop, "products/factoring-media/output/2026-05-09_xxx.md のAIっぽさを検出")
  - Skill(expert-panel, "products/factoring-media/output/2026-05-09_xxx.md をパネル評価")
```

3つ揃ったら、**Critical → Warning → Panel低スコア項目** の順で潰す。

## なぜ3層に分けるか

- **content-ops**だけだと、行単位の「AIっぽさ」（〜できます/重要なポイントは等）が見逃される
- **anti-ai-slop**だけだと、ブランド逸脱（FACCELキャラクター不在等）が見えない
- **brand-voice**だけだと、内容の説得力・読みやすさが評価できない

3層はそれぞれ違う観点で動くので、重複ではなく**直交した品質保証**になる。

## 関連
- 既存skill: `~/.claude/skills/content-ops/` (インストール済み・編集禁止)
- 既存ナレッジ: `.company/skills/brand-voice.md`（社内エージェント用のブランド定義、本subagentが参照する可能性あり）
- ブランド方針メモリ: `MEMORY.md` 上の `feedback_note_publish.md` `feedback_note_header_design.md` `ebay-roki-style.md` `saimu-media-design-direction.md`
