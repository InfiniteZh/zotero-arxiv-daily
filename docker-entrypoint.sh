#!/bin/bash
set -e

SCHEDULE="${SCHEDULE:-}"
if [ -z "$SCHEDULE" ]; then
    # No schedule - run once and exit (default behavior)
    exec uv run src/zotero_arxiv_daily/main.py "$@"
fi

# Parse schedule (format: HH:MM, e.g., "09:00")
HOUR=$(echo "$SCHEDULE" | cut -d: -f1)
MINUTE=$(echo "$SCHEDULE" | cut -d: -f2)

echo "Scheduled run at ${HOUR}:${MINUTE} daily"

while true; do
    NOW=$(date +"%H:%M")
    if [ "$NOW" = "${HOUR}:${MINUTE}" ]; then
        echo "Executing scheduled run at $(date)"
        uv run src/zotero_arxiv_daily/main.py "$@"
        echo "Run completed, sleeping until tomorrow..."
        sleep 60  # Prevent multiple runs if execution takes less than a minute
    fi
    sleep 30  # Check every 30 seconds
done
