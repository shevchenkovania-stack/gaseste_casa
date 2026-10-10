#!/usr/bin/env bash
# Apply after uploading bot/ sources: compile-check, add missing env keys, restart.
set -e
cd /opt/imobiliare/bot
ENV=/opt/imobiliare/bot/.env

echo "=== compile ==="
/opt/imobiliare/venv/bin/python -m py_compile config.py db.py main.py scheduler.py keyboards.py publish.py \
  handlers/admin.py handlers/start.py handlers/boost.py handlers/add.py handlers/browse.py handlers/profile.py
echo "compile OK"

echo "=== env ==="
add_key() { grep -q "^$1=" "$ENV" || echo "$1=$2" >> "$ENV"; }
add_key BOT_USERNAME gaseste_casa_bot
add_key NUDGE_AFTER_DAYS 2
add_key NUDGE_COOLDOWN_DAYS 4
add_key NUDGE_INTERVAL_HOURS 6
grep -E '^(CHANNEL_ID|BOT_USERNAME|WEBAPP_URL|BOOST_STARS|BOOST_DAYS|NUDGE_)' "$ENV"

echo "=== restart ==="
systemctl restart imobiliare
sleep 3
systemctl is-active imobiliare imobiliare-web

echo "=== schema ==="
/opt/imobiliare/venv/bin/python - <<'PYEOF'
import sqlite3
d = sqlite3.connect('/opt/imobiliare/data/imobiliare.db')
print('listings cols:', [r[1] for r in d.execute('PRAGMA table_info(listings)')])
PYEOF

echo "=== log ==="
journalctl -u imobiliare -n 8 --no-pager -o cat
