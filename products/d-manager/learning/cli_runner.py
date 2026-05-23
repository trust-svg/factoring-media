"""`claude -p`（Claude Code CLI）をサブプロセス起動する薄いラッパと git ヘルパ。

reviewer.py / curator.py が共用する。d-manager 本体の ai_engine._process_cli と同じく
`cwd=COMPANY_DIR`・`--dangerously-skip-permissions` で動かすが、ツールは allowedTools/disallowedTools で絞る。
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class CliResult:
    ok: bool
    stdout: str
    stderr: str
    returncode: int
    timed_out: bool


def run_claude(
    prompt: str,
    cwd: Path,
    model: str,
    allowed_tools: str,
    disallowed_tools: str,
    system_prompt_append: str,
    max_turns: int,
    timeout_sec: int,
) -> CliResult:
    cmd = [
        "claude",
        "-p",
        prompt,
        "--allowedTools",
        allowed_tools,
        "--disallowedTools",
        disallowed_tools,
        "--append-system-prompt",
        system_prompt_append,
        "--max-turns",
        str(max_turns),
        "--dangerously-skip-permissions",
    ]
    if model:
        cmd.extend(["--model", model])
    try:
        proc = subprocess.run(
            cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout_sec
        )
        return CliResult(
            ok=(proc.returncode == 0),
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
            returncode=proc.returncode,
            timed_out=False,
        )
    except subprocess.TimeoutExpired as e:
        logger.warning("claude -p timed out after %ss", timeout_sec)
        return CliResult(
            ok=False,
            stdout=(e.stdout or "") if isinstance(e.stdout, str) else "",
            stderr="timeout",
            returncode=-1,
            timed_out=True,
        )
    except FileNotFoundError:
        logger.error("`claude` CLI not found on PATH")
        return CliResult(
            ok=False,
            stdout="",
            stderr="claude-cli-not-found",
            returncode=-1,
            timed_out=False,
        )


def git_head(repo: Path) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
        ).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def git_status_short(repo: Path) -> list[str]:
    """`git status --short` の各行（"XY path" 形式）をリストで返す。"""
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "status", "--short"],
            capture_output=True,
            text=True,
        ).stdout
        return [ln for ln in out.splitlines() if ln.strip()]
    except Exception:  # noqa: BLE001
        return []


def git_checkout_paths(repo: Path, paths: list[str]) -> None:
    if not paths:
        return
    try:
        subprocess.run(
            ["git", "-C", str(repo), "checkout", "--"] + paths,
            capture_output=True,
            text=True,
        )
    except Exception:  # noqa: BLE001
        logger.exception("git checkout for out-of-bounds revert failed")


def git_clean_paths(repo: Path, paths: list[str]) -> None:
    """untracked な範囲外ファイル/ディレクトリを削除する（`git checkout --` では消せないため）。"""
    if not paths:
        return
    try:
        subprocess.run(
            ["git", "-C", str(repo), "clean", "-fd", "--"] + paths,
            capture_output=True,
            text=True,
        )
    except Exception:  # noqa: BLE001
        logger.exception("git clean for out-of-bounds untracked files failed")


def revert_out_of_bounds(
    repo: Path, status_lines: list[str], oob_paths: list[str]
) -> None:
    """範囲外パスを、tracked は `git checkout --`、untracked(`??`) は `git clean -fd --` で戻す。"""
    oob = set(oob_paths)
    tracked: list[str] = []
    untracked: list[str] = []
    for ln in status_lines:
        p = parse_status_path(ln)
        if p not in oob:
            continue
        (untracked if ln.startswith("??") else tracked).append(p)
    git_checkout_paths(repo, tracked)
    git_clean_paths(repo, untracked)


def parse_status_path(line: str) -> str:
    """`git status --short` の1行からパス部分を取り出す（"?? path" / " M path" / "A  path" 等）。"""
    # 先頭2文字 = ステータス、その後スペース1つ、残りがパス（リネームは ' -> ' を含む → 右側を取る）
    rest = line[3:] if len(line) > 3 else line.strip()
    if " -> " in rest:
        rest = rest.split(" -> ", 1)[1]
    return rest.strip().strip('"')


# 学習ループが書き込んでよい .company/ 配下のディレクトリ/ファイル（プレフィックス一致で判定）
ALLOWED_WRITE_PREFIXES = (
    "skills/",
    "secretary/memory/",
    "secretary/rules.md",
)


def out_of_bounds_paths(
    repo: Path, status_lines: list[str], extra_allowed: tuple = ()
) -> list[str]:
    """git status の変更パスのうち、許可プレフィックスにも extra_allowed（例: `<dept>/knowledge/`）にも
    該当しないものを返す。`<dept>/knowledge/` は固定列挙が難しいので、呼び出し側が
    `("operations/knowledge/", "research/knowledge/", ...)` のように渡すか、後述の DEPT_KNOWLEDGE_PREFIXES を使う。
    """
    bad = []
    allowed = ALLOWED_WRITE_PREFIXES + tuple(extra_allowed)
    for ln in status_lines:
        p = parse_status_path(ln)
        if not any(p.startswith(a) for a in allowed):
            bad.append(p)
    return bad


# .company/<dept>/knowledge/ の dept 一覧（CLAUDE.md の組織図に対応）
DEPT_KNOWLEDGE_PREFIXES = tuple(
    f"{d}/knowledge/"
    for d in (
        "operations",
        "product",
        "marketing",
        "finance",
        "research",
        "strategy",
        "secretary",
    )
)
