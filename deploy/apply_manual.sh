#!/usr/bin/env bash
# Apply manual MDL payment rail: compile check, env keys, restart, verify callbacks wiring.
set -e
cd /opt/imobiliare/bot
ENV=/opt/imobiliare/bot/.env

echo "=== compile ==="
/opt/imobiliare/venv/bin/python -m py_compile config.py db.py keyboards.py scheduler.py publish.py main.py \
  handlers/boost.py handlers/admin.py handlers/start.py handlers/add.py handlers/browse.py handlers/profile.py
echo "compile OK"

echo "=== env ==="
add_key() { grep -q "^$1=" "$ENV" || echo "$1=$2" >> "$ENV"; }
add_key BOOST_MDL 100
add_key PAY_INFO ""
grep -E '^(BOOST_STARS|BOOST_DAYS|BOOST_MDL|PAY_INFO|CHANNEL_ID|BOT_USERNAME)=' "$ENV"

echo "=== restart ==="
systemctl restart imobiliare
sleep 3
systemctl is-active imobiliare imobiliare-web

echo "=== wiring ==="
/opt/imobiliare/venv/bin/python - <<'PYEOF'
import sys
sys.path.insert(0, "/opt/imobiliare/bot")
import config, db
from handlers import boost, admin
print("BOOST_MDL =", config.BOOST_MDL, "| PAY_INFO set:", bool(config.PAY_INFO))
print("boost handlers:", [h.callback.name for h in boost.router.message.handlers if hasattr(h, "callback")][:8])
print("admin manapp/manrej registered:",
      any("manapp" in str(getattr(h, "filters", "")) for h in admin.router.callback_query.handlers))
PYEOF

echo "=== schema ==="
/opt/imobiliare/venv/bin/python - <<'PYEOF'
import sqlite3
d = sqlite3.connect('/opt/imobiliare/data/imobiliare.db')
print('payments cols:', [r[1] for r in d.execute('PRAGMA table_info(payments)')])
print('boost statuses:', d.execute('select status, count(*) from boosts group by status').fetchall())
PYEOF

echo "=== log ==="
journalctl -u imobiliare -n 6 --no-pager -o cat
