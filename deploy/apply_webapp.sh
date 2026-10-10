#!/usr/bin/env bash
# Apply webapp + bot updates on server. Files must be pre-copied to /opt/imobiliare/bot.
set -e
cd /opt/imobiliare/bot
/opt/imobiliare/venv/bin/python -m py_compile config.py keyboards.py publish.py handlers/boost.py handlers/start.py handlers/admin.py webapp/app.py
echo "compile OK"

cp /tmp/imobiliare-web.service /etc/systemd/system/imobiliare-web.service
systemctl daemon-reload
systemctl enable imobiliare-web
systemctl restart imobiliare-web
sleep 2
echo "--- /api/stats:"; curl -s http://127.0.0.1:8085/api/stats; echo

echo "--- inserting temp listing"
/opt/imobiliare/venv/bin/python - <<'EOF'
import sqlite3
db = sqlite3.connect('/opt/imobiliare/data/imobiliare.db')
cur = db.execute("INSERT INTO listings (user_id,deal,ptype,price,currency,district,status,photos) VALUES (1,'rent','apartment',450,'EUR','Центр','active','[]')")
db.commit(); print('temp listing id:', cur.lastrowid)
EOF
echo "--- /api/listings:"; curl -s "http://127.0.0.1:8085/api/listings?deal=rent" | head -c 500; echo

echo "--- restarting bot"
systemctl restart imobiliare
sleep 3
systemctl is-active imobiliare imobiliare-web
journalctl -u imobiliare -n 3 --no-pager
