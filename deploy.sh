#!/usr/bin/env bash
cd "$(dirname "$0")"

LOG_DIR="logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/deploy_$(date +%Y-%m-%d_%H%M%S).log"

# Clean up logs older than 5 days
find "$LOG_DIR" -name "deploy_*.log" -mtime +5 -delete

{
    echo "=== Deploy started: $(date) ==="

    python main.py --update --no-open

    git add docs/index.html docs/forecast.html
    if git diff --cached --quiet; then
        echo "No changes to commit."
    else
        git commit -m "Update dashboard $(date +%Y-%m-%d_%H:%M)"
        git push
    fi

    echo "=== Deploy finished: $(date) ==="
} >> "$LOG_FILE" 2>&1
