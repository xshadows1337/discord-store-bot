#!/bin/bash
# ─────────────────────────────────────────────────────────────
#  WinterNode / VPS one-time setup script
#  Run once as root (or with sudo) after SFTPing the folder.
#  Usage:  bash setup.sh
# ─────────────────────────────────────────────────────────────
set -e

BOTDIR="$(cd "$(dirname "$0")" && pwd)"
SRCDIR="$BOTDIR/src"
VENV="$BOTDIR/venv"
SERVICE_NAME="abysshub-bot"

echo "=== Abyss Hub Bot — VPS Setup ==="
echo "Bot directory: $BOTDIR"

# ── 1. Python 3.12 ────────────────────────────────────────────
if ! command -v python3.12 &>/dev/null; then
    echo "→ Installing Python 3.12..."
    apt-get update -qq
    apt-get install -y software-properties-common
    add-apt-repository -y ppa:deadsnakes/ppa
    apt-get update -qq
    apt-get install -y python3.12 python3.12-venv python3.12-dev
else
    echo "→ Python 3.12 already installed: $(python3.12 --version)"
fi

# ── 2. Virtual environment ─────────────────────────────────────
if [ ! -d "$VENV" ]; then
    echo "→ Creating virtual environment at $VENV..."
    python3.12 -m venv "$VENV"
fi

echo "→ Installing Python dependencies..."
"$VENV/bin/pip" install --upgrade pip -q
"$VENV/bin/pip" install -r "$BOTDIR/requirements.txt" -q
echo "   Done."

# ── 3. Data directories ────────────────────────────────────────
echo "→ Creating data directories..."
mkdir -p "$SRCDIR/delivered_orders" "$SRCDIR/products"

# ── 4. .env file ──────────────────────────────────────────────
if [ ! -f "$SRCDIR/.env" ]; then
    echo ""
    echo "  ⚠️  No .env file found!"
    echo "  Copy $SRCDIR/.env.example to $SRCDIR/.env and fill in your values."
    echo "  Then re-run:  bash setup.sh"
    echo ""
fi

# ── 5. systemd service ────────────────────────────────────────
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
echo "→ Installing systemd service: $SERVICE_NAME"
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Abyss Hub Discord Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=$SRCDIR
ExecStart=$VENV/bin/python main.py
Restart=on-failure
RestartSec=10
StandardOutput=append:$BOTDIR/bot.log
StandardError=append:$BOTDIR/bot.log
Environment=PYTHONUTF8=1

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
echo "   Service installed and enabled."

echo ""
echo "=== Setup complete! ==="
echo ""
echo "Next steps:"
echo "  1. Edit $SRCDIR/.env with your bot token and other secrets"
echo "  2. Start the bot:    systemctl start $SERVICE_NAME"
echo "  3. Check status:     systemctl status $SERVICE_NAME"
echo "  4. View logs:        tail -f $BOTDIR/bot.log"
echo ""
