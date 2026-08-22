#!/usr/bin/env bash
# Push Capital Steward Engine to GitHub.
# Run this ON YOUR MACHINE (after cloning or unzipping the bundle), with your own
# GitHub credentials. The sandbox has no GitHub authentication and must not hold it.
set -euo pipefail

REMOTE="${1:-https://github.com/ramkivs/CapStew-Engine.git}"

cd "$(dirname "$0")/.."

# Ensure we're a git repo (the workspace snapshot may drop .git/config between sessions).
if [ ! -d .git ]; then
  echo "re-initialising git (no .git found)…"
  git init -q
  git config user.name  "Ramki VS"
  git config user.email "you@example.com"   # ← replace with your GitHub email
fi

git branch -M main 2>/dev/null || true

if git remote get-url origin >/dev/null 2>&1; then
  echo "remote 'origin' already set: $(git remote get-url origin)"
else
  git remote add origin "$REMOTE"
  echo "added remote origin → $REMOTE"
fi

echo
echo "pushing main + tags…"
git add -A
git commit -q -m "Capital Steward Engine v1.0.0" 2>/dev/null || echo "  (nothing new to commit)"
git push -u origin main
git push --tags

echo
echo "Done. Verify at: ${REMOTE%.git}"
