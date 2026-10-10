#!/usr/bin/env bash
set -e
cd /opt/imobiliare/bot
/opt/imobiliare/venv/bin/python - <<'PYEOF'
import sys
sys.path.insert(0, "/opt/imobiliare/bot")
import config
from handlers import boost, admin

def names(handlers):
    out = []
    for h in handlers:
        cb = getattr(h, "callback", h)
        out.append(getattr(cb, "__name__", str(cb)))
    return out

print("BOOST_MDL =", config.BOOST_MDL, "| PAY_INFO set:", bool(config.PAY_INFO))
print("boost callback handlers:", names(boost.router.callback_query.handlers))
print("admin callback handlers:", names(admin.router.callback_query.handlers))
PYEOF
echo "=== schema ==="
/opt/imobiliare/venv/bin/python - <<'PYEOF'
import sqlite3
d = sqlite3.connect('/opt/imobiliare/data/imobiliare.db')
print('payments cols:', [r[1] for r in d.execute('PRAGMA table_info(payments)')])
print('listings cols has nudged_at:', any(r[1] == 'nudged_at' for r in d.execute('PRAGMA table_info(listings)')))
print('boost statuses:', d.execute('select status, count(*) from boosts group by status').fetchall())
print('payments:', d.execute('select count(*), currency from payments group by currency').fetchall())
PYEOF
echo "=== services ==="
systemctl is-active imobiliare imobiliare-web
echo "=== log ==="
journalctl -u imobiliare -n 6 --no-pager -o cat
