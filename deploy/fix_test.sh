#!/usr/bin/env bash
set -e
/opt/imobiliare/venv/bin/python - <<'PYEOF'
import sqlite3
db = sqlite3.connect('/opt/imobiliare/data/imobiliare.db')
n = db.execute("delete from listings where description like '%ТЕХНИЧЕСКИЙ ТЕСТ%'").rowcount
db.commit()
print('cleaned old test rows:', n)
PYEOF
systemctl restart imobiliare
cd /opt/imobiliare/bot
/opt/imobiliare/venv/bin/python /tmp/test_publish.py
systemctl is-active imobiliare imobiliare-web
