#!/bin/bash
# Auto-update script for btcticker.
# Run periodically via systemd timer or cron.
# Pulls from origin if behind, restarts the service, and rolls back if it fails.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE="btcticker"
BRANCH="main"
HEALTH_WAIT=15   # seconds to wait before checking service health

cd "$REPO_DIR"

git fetch origin "$BRANCH" --quiet

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse "origin/$BRANCH")

if [ "$LOCAL" = "$REMOTE" ]; then
    exit 0
fi

PREV_COMMIT="$LOCAL"
echo "$(date -Iseconds) New commits detected — updating from ${PREV_COMMIT:0:7} to ${REMOTE:0:7}"

git pull origin "$BRANCH" --ff-only --quiet
sudo systemctl restart "$SERVICE"

sleep "$HEALTH_WAIT"

if systemctl is-active --quiet "$SERVICE"; then
    echo "$(date -Iseconds) Update OK — running $(git rev-parse --short HEAD)"
else
    echo "$(date -Iseconds) Service failed after update — rolling back to $PREV_COMMIT"
    git checkout "$PREV_COMMIT" --quiet
    sudo systemctl restart "$SERVICE"
    sleep 5
    if systemctl is-active --quiet "$SERVICE"; then
        echo "$(date -Iseconds) Rollback successful"
    else
        echo "$(date -Iseconds) Rollback also failed — manual intervention required" >&2
    fi
    exit 1
fi
