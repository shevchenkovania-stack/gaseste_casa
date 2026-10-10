#!/usr/bin/env bash
set -e
echo "=== log (last 20) ==="
journalctl -u imobiliare -n 20 --no-pager -o cat
echo "=== schema ==="
/opt/imobiliare/venv/bin/python - <<'PYEOF'
import sqlite3
d = sqlite3.connect('/opt/imobiliare/data/imobiliare.db')
print('has nudged_at:', any(r[1] == 'nudged_at' for r in d.execute('PRAGMA table_info(listings)')))
print('users:', d.execute('select count(*) from users').fetchone()[0])
print('listings:', d.execute('select count(*) from listings').fetchone()[0])
PYEOF
echo "=== import check ==="
cd /opt/imobiliare/bot
/opt/imobiliare/venv/bin/python -c "import config; print('BOT_URL', config.BOT_URL); print('CHANNEL_URL', config.CHANNEL_URL)"
