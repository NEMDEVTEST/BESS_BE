#!/usr/bin/env bash
cd "$(dirname "$0")"

python main.py --update --no-open

git add docs/index.html
git diff --cached --quiet && exit 0   # nothing changed, skip

git commit -m "Update dashboard $(date +%Y-%m-%d_%H:%M)"
git push
