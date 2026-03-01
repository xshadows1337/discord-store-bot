#!/bin/bash
# ─────────────────────────────────────────────────────────────
#  Start the bot manually (without systemd).
#  Useful for testing. For production use systemd instead:
#    systemctl start abysshub-bot
# ─────────────────────────────────────────────────────────────
BOTDIR="$(cd "$(dirname "$0")" && pwd)"
SRCDIR="$BOTDIR/src"
VENV="$BOTDIR/venv"

if [ ! -d "$VENV" ]; then
    echo "Virtual environment not found. Run setup.sh first."
    exit 1
fi

if [ ! -f "$SRCDIR/.env" ]; then
    echo "Warning: $SRCDIR/.env not found. Using settings.json fallback."
fi

cd "$SRCDIR"
PYTHONUTF8=1 exec "$VENV/bin/python" main.py
