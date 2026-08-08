#!/bin/bash
# setup_background_tracker.sh
#
# Installs / removes CADDY's background job tracker cron job.
#
# NOTE: all the real logic lives in background_tracker.py (single source of
# truth). This script just calls it, so running the same commands from inside
# CADDY ("enable background tracker" / "disable background tracker") and from
# this script can never drift apart.
#
# Usage:
#   ./setup_background_tracker.sh            # install, check every 30 minutes
#   ./setup_background_tracker.sh 60         # install, check every 60 minutes
#   ./setup_background_tracker.sh remove     # uninstall
#
# After installing, view logs with: tail -f background_tracker.log

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
INTERVAL_MIN="${1:-30}"
PYTHON="$PROJECT_DIR/venv/bin/python"
if [ ! -x "$PYTHON" ]; then
    PYTHON="$(command -v python3)"
fi

echo "=============================================="
echo "🤖 CADDY Background Job Tracker"
echo "=============================================="

if [ ! -x "$PYTHON" ]; then
    echo "❌ Python not found. Install dependencies first (see README.md)."
    exit 1
fi

if [ "$INTERVAL_MIN" = "remove" ]; then
    echo "🗑  Removing background tracker from cron..."
    "$PYTHON" -c "from background_tracker import remove_cron_tracker; import sys; sys.exit(0 if remove_cron_tracker() else 1)"
    echo "✓ Removed. Jobs already collected are still in jobs_results.json"
    exit 0
fi

# Validate interval
if ! [[ "$INTERVAL_MIN" =~ ^[0-9]+$ ]] || [ "$INTERVAL_MIN" -lt 1 ]; then
    echo "❌ Interval must be a positive number of minutes (got: $INTERVAL_MIN)"
    exit 1
fi

# Check python & network deps
echo "📦 Python: $PYTHON"
if ! "$PYTHON" -c "import requests, bs4" 2>/dev/null; then
    echo "❌ Missing dependencies. Run: $PYTHON -m pip install -r $PROJECT_DIR/requirements.txt"
    exit 1
fi

# Install via the Python module (keeps the cron format in one place)
echo "⏰ Installing cron job (every $INTERVAL_MIN minutes)..."
if ! "$PYTHON" -c "from background_tracker import install_cron_tracker; import sys; sys.exit(0 if install_cron_tracker($INTERVAL_MIN) else 1)"; then
    echo "❌ Could not install the cron job. Check background_tracker.log for details."
    exit 1
fi

echo "✓ Installed! The tracker now runs automatically every $INTERVAL_MIN minutes."
echo ""
echo "Next steps:"
echo "  1. Add job searches in CADDY first:  python main.py"
echo "     (e.g. 'add job search: Python Developer, Remote')"
echo "  2. The tracker will start picking up your searches on the next run."
echo "  3. Inside CADDY, type 'latest jobs' to see what was collected."
echo ""
echo "📄 Logs: tail -f $PROJECT_DIR/background_tracker.log"
echo "🔧 Uninstall later: ./setup_background_tracker.sh remove"
