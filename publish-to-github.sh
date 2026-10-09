#!/bin/bash
set -e
# JustSing — Publish to GitHub repo JustSing
# Usage: ./publish-to-github.sh YOUR_GITHUB_USERNAME
# Or set GITHUB_USER env var

USER=${1:-$GITHUB_USER}
if [ -z "$USER" ]; then
  echo "Usage: $0 YOUR_GITHUB_USERNAME"
  echo "Example: $0 ramshrestha"
  echo "Or: GITHUB_USER=ramshrestha ./publish-to-github.sh"
  exit 1
fi

REPO="JustSing"
REMOTE="https://github.com/$USER/$REPO.git"

echo "📦 Preparing to push to $REMOTE"
echo ""

# Check if repo exists locally
if [ ! -d .git ]; then
  git init
  git add .
  git commit -m "feat: JustSing MVP v0.2"
fi

# Rename master to main (GitHub default)
git branch -M main 2>/dev/null || true

# Check if remote exists
if git remote | grep -q origin; then
  git remote remove origin
fi

git remote add origin $REMOTE

echo "🚀 Pushing to GitHub..."
echo "   If prompted, enter your GitHub Personal Access Token (not password)"
echo "   Create token at: https://github.com/settings/tokens (classic, repo scope)"
echo ""

# Try push
if git push -u origin main; then
  echo ""
  echo "✅ Published! View at: https://github.com/$USER/$REPO"
else
  echo ""
  echo "❌ Push failed. Common fixes:"
  echo "1. Create empty repo on GitHub first: https://github.com/new -> Name: JustSing (don't init with README)"
  echo "2. If repo exists and has README, pull first: git pull origin main --allow-unrelated-histories"
  echo "3. Use PAT token, not password. Create at https://github.com/settings/tokens"
  echo "4. Or use SSH: git remote set-url origin git@github.com:$USER/$REPO.git"
fi
