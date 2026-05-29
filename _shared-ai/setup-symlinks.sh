#!/usr/bin/env bash
# Regenerate symlinks so Claude Code and Codex both load the shared skills
# from the single source of truth at _shared-ai/skills/.
# Idempotent: safe to re-run. Add new skill names to SKILLS and re-run.
#
# NOTE: writing into ~/.codex/skills requires the sandbox allowWrite entry
#       "/Users/Mac_air/.codex/skills" in ~/.claude/settings.json, and a
#       Claude Code restart to take effect. ~/.codex as a whole must NOT be
#       allowed (it holds auth.json / config.toml).

set -euo pipefail

WORKSPACE="/Users/Mac_air/Claude-Workspace"
SHARED="$WORKSPACE/_shared-ai/skills"
CLAUDE_SKILLS="$HOME/.claude/skills"
CODEX_SKILLS="$HOME/.codex/skills"
AGENTS_SKILLS="$WORKSPACE/.agents/skills"

SKILLS=(
  skill-quality-checker
  mcp-audit
  factcheck-ai-cross
  codex-handoff
)

if [ ! -d "$SHARED" ]; then
  echo "ERROR: source of truth not found: $SHARED" >&2
  exit 1
fi

mkdir -p "$CLAUDE_SKILLS" "$AGENTS_SKILLS"
# ~/.codex/skills may be sandbox-restricted; create only if writable.
mkdir -p "$CODEX_SKILLS" 2>/dev/null || true

for s in "${SKILLS[@]}"; do
  if [ ! -d "$SHARED/$s" ]; then
    echo "skip (missing): $SHARED/$s" >&2
    continue
  fi

  # Claude (primary, absolute)
  ln -sfn "$SHARED/$s" "$CLAUDE_SKILLS/$s"
  echo "claude : $CLAUDE_SKILLS/$s -> $SHARED/$s"

  # Codex user scope (primary, absolute, official 1-level layout)
  if mkdir -p "$CODEX_SKILLS" 2>/dev/null && [ -w "$CODEX_SKILLS" ]; then
    ln -sfn "$SHARED/$s" "$CODEX_SKILLS/$s"
    echo "codex  : $CODEX_SKILLS/$s -> $SHARED/$s"
  else
    echo "codex  : SKIP $CODEX_SKILLS not writable (add sandbox allowWrite + restart)" >&2
  fi

  # Codex repo scope (auxiliary, relative)
  ln -sfn "../../_shared-ai/skills/$s" "$AGENTS_SKILLS/$s"
  echo "agents : $AGENTS_SKILLS/$s -> ../../_shared-ai/skills/$s"
done

echo "Done. Restart Codex to pick up ~/.codex/skills changes."
