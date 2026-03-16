#!/bin/bash
# ============================================================
# Claude Workspace セットアップスクリプト
# Mac Mini（または新しいマシン）で実行してワークスペースを再構築
# ============================================================

set -e

WORKSPACE="${1:-$HOME/Desktop/Claude Workspace}"
echo "📁 Workspace: $WORKSPACE"

# ------ メインリポジトリ ------
if [ ! -d "$WORKSPACE/.git" ]; then
  echo "🔄 Cloning main repository..."
  git clone https://github.com/trust-svg/claude-workspace.git "$WORKSPACE"
else
  echo "✅ Main repo already exists, pulling latest..."
  cd "$WORKSPACE" && git pull
fi

cd "$WORKSPACE"

# ------ サブリポジトリ（独自.gitで管理） ------
declare -A REPOS=(
  ["products/ai-uranai"]="https://github.com/trust-svg/ai-uranai.git"
  ["products/ebay-inventory-tool"]="https://github.com/trust-svg/ebay-inventory-tool.git"
  ["products/ebay-listing-generator"]="https://github.com/trust-svg/ebay-listing-generator.git"
  ["products/video-text-remover"]="https://github.com/trust-svg/video-text-remover.git"
  ["reusable/matching-lp"]="https://github.com/trust-svg/matching-lp.git"
  ["ccskill-nanobanana"]="https://github.com/feedtailor/ccskill-nanobanana.git"
  ["tmp/cc-secretary"]="https://github.com/Shin-sibainu/cc-secretary.git"
  ["tmp/cc-company"]="https://github.com/Shin-sibainu/cc-company.git"
)

for dir in "${!REPOS[@]}"; do
  url="${REPOS[$dir]}"
  target="$WORKSPACE/$dir"
  if [ ! -d "$target/.git" ]; then
    echo "🔄 Cloning $dir..."
    mkdir -p "$(dirname "$target")"
    git clone "$url" "$target"
  else
    echo "✅ $dir already exists, pulling latest..."
    cd "$target" && git pull
    cd "$WORKSPACE"
  fi
done

# ------ Python仮想環境の再構築 ------
echo ""
echo "🐍 Setting up Python virtual environments..."

VENV_DIRS=(
  "products/ai-uranai/ai-fortune"
  "products/ebay-agent"
  "products/ebay-inventory-tool"
  "products/deal-watcher"
  "products/b-manager"
  "products/ebay-listing-optimizer"
  "marketing/meta-ads"
)

for dir in "${VENV_DIRS[@]}"; do
  req="$WORKSPACE/$dir/requirements.txt"
  if [ -f "$req" ]; then
    echo "  📦 $dir..."
    cd "$WORKSPACE/$dir"
    if [ ! -d ".venv" ] && [ ! -d "venv" ]; then
      python3 -m venv .venv
      .venv/bin/pip install -q -r requirements.txt
    else
      echo "    (venv already exists, skipping)"
    fi
    cd "$WORKSPACE"
  fi
done

# ------ Google Driveからマーケティング資産をリンク（任意） ------
GDRIVE="$HOME/Library/CloudStorage/GoogleDrive-otsuka@trustlink-tk.com/マイドライブ/Claude Workspace/marketing"
if [ -d "$GDRIVE" ]; then
  echo ""
  echo "🔗 Google Drive marketing assets found."
  echo "   Location: $GDRIVE"
  echo "   (Manually symlink if needed: ln -s \"$GDRIVE\" \"$WORKSPACE/marketing-gdrive\")"
fi

# ------ .envファイルの復元案内 ------
GDRIVE_ENV="$HOME/Library/CloudStorage/GoogleDrive-otsuka@trustlink-tk.com/マイドライブ/Claude Workspace/env-backup.zip"
if [ -f "$GDRIVE_ENV" ]; then
  echo ""
  echo "🔐 .env backup found on Google Drive."
  echo "   To restore: cd \"$WORKSPACE\" && unzip -o \"$GDRIVE_ENV\""
else
  echo ""
  echo "⚠️  No .env backup found on Google Drive."
  echo "   Copy .env files manually from your other machine."
fi

echo ""
echo "============================================================"
echo "✅ Workspace setup complete!"
echo ""
echo "Remaining manual steps:"
echo "  1. Copy/restore .env files (see above)"
echo "  2. SQLite databases are local-only (will be recreated by apps)"
echo "  3. Install Claude Code skills if needed"
echo "============================================================"
