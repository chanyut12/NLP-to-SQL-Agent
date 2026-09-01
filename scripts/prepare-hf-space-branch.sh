#!/usr/bin/env bash
# Build (or refresh) the deploy/hf-space branch: only the files the running
# service needs on a Hugging Face Gradio Space, plus the Space config. The Space
# repo is PUBLIC, so eval/, docs/, scripts/, tests/, internal .md files etc. are
# left out. See docs/DEPLOYMENT.md.
#
#   git switch main && git pull                 # start from what you want to ship
#   ./scripts/prepare-hf-space-branch.sh
#   git push space deploy/hf-space:main --force # first push (Space has an initial commit)
set -euo pipefail

SOURCE_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
DEPLOY_BRANCH="deploy/hf-space"

# What the service actually imports at runtime + the Space entrypoint/config.
KEEP_REGEX='^(api/|core/|profiles/|web/)|^(app\.py|requirements\.txt|README\.md|\.python-version|Dockerfile)$'

echo "Building $DEPLOY_BRANCH from $SOURCE_BRANCH ..."
git switch -C "$DEPLOY_BRANCH" >/dev/null

# Drop everything not matched by KEEP_REGEX (index only; working tree untouched).
git ls-files | grep -vE "$KEEP_REGEX" | tr '\n' '\0' | xargs -0 --no-run-if-empty git rm -q --cached

# Prepend the HF Space frontmatter to README.md (once).
if ! head -1 README.md | grep -q '^---$'; then
  tmp="$(mktemp)"
  cat > "$tmp" <<'EOF'
---
title: STS NL-to-SQL
sdk: gradio
app_file: app.py
pinned: false
---

EOF
  cat README.md >> "$tmp"
  mv "$tmp" README.md
  git add README.md
fi

git commit -q -m "chore(deploy): HF Space build (from $SOURCE_BRANCH)"

echo
echo "✅ $DEPLOY_BRANCH ready — files that will land in the Space repo:"
git ls-files | sed 's/^/   /'
echo
echo "next:"
echo "   git remote get-url space >/dev/null 2>&1 || git remote add space https://huggingface.co/spaces/<user>/<space>"
echo "   git push space $DEPLOY_BRANCH:main --force"
echo "   git switch $SOURCE_BRANCH"
