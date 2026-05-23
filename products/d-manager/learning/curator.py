"""週次スキルキュレーター — `.company/skills/` を棚卸し（統合・アーカイブ・frontmatter 修正）。

# Adapted from Hermes Agent (MIT) — github.com/NousResearch/hermes-agent
# CURATOR_PERSONA / CURATOR_PROMPT は Hermes の CURATOR_REVIEW_PROMPT をベースに移植。
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import re
import tarfile
from pathlib import Path
from typing import Optional

from . import cli_runner

logger = logging.getLogger(__name__)

_SUMMARY_RE = re.compile(r"<summary>(.*?)</summary>", re.DOTALL)


def _parse_summary(text: str) -> Optional[str]:
    m = list(_SUMMARY_RE.finditer(text or ""))
    return m[-1].group(1).strip() if m else None


def _make_snapshot(company_dir: Path, keep: int = 8) -> None:
    """`.company/skills/` を tar.gz スナップショット。直近 `keep` 世代だけ残す。"""
    snap_dir = company_dir / "skills" / ".snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    name = f"skills-{dt.date.today().strftime('%Y-%m-%d')}.tar.gz"
    path = snap_dir / name
    skills_dir = company_dir / "skills"
    with tarfile.open(path, "w:gz") as tar:
        for entry in skills_dir.iterdir():
            if entry.name == ".snapshots":
                continue
            tar.add(entry, arcname=f"skills/{entry.name}")
    snaps = sorted(snap_dir.glob("skills-*.tar.gz"))
    for old in snaps[:-keep]:
        old.unlink(missing_ok=True)


def _recent_skill_hits(skill_hits_path: Path, days: int = 90) -> list[str]:
    """直近 `days` 日に1回以上ヒットしたスキル名の一覧。"""
    if not skill_hits_path.exists():
        return []
    cutoff = (dt.date.today() - dt.timedelta(days=days)).strftime("%Y-%m-%d")
    hits = set()
    for ln in skill_hits_path.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            rec = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if rec.get("date", "") >= cutoff:
            hits.add(rec.get("skill", ""))
    return sorted(h for h in hits if h)


def _skill_overview(company_dir: Path, max_head_chars: int = 600) -> str:
    skills_dir = company_dir / "skills"
    lines = []
    if not skills_dir.exists():
        return "(skills ディレクトリなし)"
    for entry in sorted(skills_dir.iterdir()):
        if entry.name.startswith("."):
            continue
        if entry.is_file() and entry.suffix == ".md":
            lines.append(
                f"### skills/{entry.name}\n"
                + entry.read_text(encoding="utf-8")[:max_head_chars]
            )
        elif entry.is_dir() and (entry / "SKILL.md").exists():
            lines.append(
                f"### skills/{entry.name}/SKILL.md\n"
                + (entry / "SKILL.md").read_text(encoding="utf-8")[:max_head_chars]
            )
    return "\n\n".join(lines)


CURATOR_PERSONA = """あなたは TrustLink のスキルキュレーターです。12名のAI社員のような人格は持ちません。
`.company/skills/` の健全性を保つことだけが仕事です。ファイルの Read/Write/Edit/Glob/Grep のみ使えます。
削除は決してしてはいけません（アーカイブ＝`.company/skills/.archive/` への移動のみ）。判断に迷ったら触らないでください。"""


def build_curator_prompt(
    skill_overview: str, recent_hits: list[str], dryrun: bool = False
) -> str:
    hits_str = ", ".join(recent_hits) if recent_hits else "(記録なし)"
    dryrun_note = (
        "\n\n【ドライランモード】ファイルは一切書くな・移動するな（Write/Edit するな）。"
        "もし本番なら何をどう変えるつもりだったか（merge / archive / fix それぞれの対象ファイルと理由）を <summary> に詳細に列挙せよ。"
        if dryrun
        else ""
    )
    return f"""`.company/skills/` 全体を棚卸ししてください。やることは次の3つだけです。{dryrun_note}
1. 内容が重なる狭いスキルを「クラスレベルの包括スキル」に統合する（元スキルの手順・品質チェックリスト・失敗時の対応を取りこぼさず織り込み、元ファイルは `.company/skills/.archive/` へ移動）。
2. 明らかに陳腐化・未使用のスキルを `.company/skills/.archive/` に移動する（削除ではなく移動）。
3. frontmatter（`name` / `owner` / `trigger`）が崩れているものを直す。

制約:
- 削除は絶対にしない。アーカイブ＝移動のみ。
- 迷ったら触らない（保守的に）。
- 1回の棚卸しで触るスキルは最大5件まで。残りは来週。
- スキル本文が長くなりすぎているもの（概ね80-100行超）は、骨子だけ `<name>/SKILL.md` に残し、詳細・長いサンプル・チェックリストを `<name>/references/*.md` に分ける形に整形してよい。
- `.company/skills/README.md` のスキル一覧も実態に合わせて更新する。

参考: 直近90日に1回以上参照されたスキル: {hits_str}（記録に無い＝最近使われていない候補。ただし即アーカイブの根拠にはしない。判断材料に留める）

## 現在のスキル一覧（各冒頭）
{skill_overview}

---
作業が終わったら、最後に1つだけ次の形式で `<summary>` を返してください:
`<summary>before=<件数> after=<件数> merged=[...] archived=[...] created=[...] fixed=[...]</summary>`
"""


def run_curation(
    company_dir: Path,
    model: str,
    skill_hits_path: Path,
    *,
    allowed_tools: str = "Read Write Edit Glob Grep",
    dryrun_allowed_tools: str = "Read Glob Grep",
    disallowed_tools: str = "Bash WebFetch WebSearch Task",
    max_turns: int = 25,
    timeout_sec: int = 600,
    snapshot_keep: int = 8,
    dryrun: bool = False,
) -> dict:
    """戻り値: {status, note, summary, head_before, out_of_bounds, dryrun}."""
    head_before = cli_runner.git_head(company_dir)
    if not dryrun:
        try:
            _make_snapshot(company_dir, keep=snapshot_keep)
        except Exception:  # noqa: BLE001
            logger.exception("skills スナップショット作成に失敗（処理は続行）")

    overview = _skill_overview(company_dir)
    hits = _recent_skill_hits(skill_hits_path)
    prompt = build_curator_prompt(overview, hits, dryrun=dryrun)
    effective_allowed_tools = dryrun_allowed_tools if dryrun else allowed_tools
    result = cli_runner.run_claude(
        prompt=prompt,
        cwd=company_dir,
        model=model,
        allowed_tools=effective_allowed_tools,
        disallowed_tools=disallowed_tools,
        system_prompt_append=CURATOR_PERSONA,
        max_turns=max_turns,
        timeout_sec=timeout_sec,
    )

    # dryrun 時は書き込み不可なので変更は起きない。
    # git_status_short を実行すると事前の uncommitted changes を oob 判定してしまい
    # revert_out_of_bounds が既存変更を消す事故につながるためスキップする。
    if dryrun:
        oob: list[str] = []
    else:
        status_lines = cli_runner.git_status_short(company_dir)
        oob = []
        for ln in status_lines:
            p = cli_runner.parse_status_path(ln)
            if not (p.startswith("skills/")):
                oob.append(p)
        if oob:
            cli_runner.revert_out_of_bounds(company_dir, status_lines, oob)
            logger.warning("curator touched out-of-bounds paths, reverted: %s", oob)

    if result.timed_out:
        return {
            "status": "error",
            "note": "timeout",
            "summary": "",
            "head_before": head_before,
            "out_of_bounds": oob,
            "dryrun": dryrun,
        }
    if not result.ok:
        return {
            "status": "error",
            "note": f"exit={result.returncode}: {result.stderr[-300:]}",
            "summary": "",
            "head_before": head_before,
            "out_of_bounds": oob,
            "dryrun": dryrun,
        }
    summary = _parse_summary(result.stdout)
    if summary is None:
        return {
            "status": "error",
            "note": "no_summary",
            "summary": "",
            "head_before": head_before,
            "out_of_bounds": oob,
            "dryrun": dryrun,
        }
    return {
        "status": "done",
        "note": "",
        "summary": summary,
        "head_before": head_before,
        "out_of_bounds": oob,
        "dryrun": dryrun,
    }
