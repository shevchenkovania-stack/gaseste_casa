#!/usr/bin/env bash
set -e
echo "=== services ==="
systemctl is-active imobiliare imobiliare-web
echo "=== db counts ==="
/opt/imobiliare/venv/bin/python - <<'PYEOF'
import sqlite3
d = sqlite3.connect('/opt/imobiliare/data/imobiliare.db')
for k in ('users', 'listings', 'boosts', 'payments', 'events'):
    print(k, d.execute(f'select count(*) from {k}').fetchone()[0])
print('listing statuses:', d.execute("select status, count(*) from listings group by status").fetchall())
print('events:', d.execute("select name, count(*) from events group by name").fetchall())
PYEOF
echo "=== env keys ==="
grep -oE '^[A-Z_]+' /opt/imobiliare/bot/.env
echo "=== channel id ==="
grep '^CHANNEL_ID' /opt/imobiliare/bot/.env
echo "=== webapp stats ==="
curl -s --max-time 5 http://127.0.0.1:8085/api/stats
echo
echo "=== last bot log ==="
journalctl -u imobiliare -n 5 --no-pager -o cat
