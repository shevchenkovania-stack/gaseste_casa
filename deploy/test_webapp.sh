#!/usr/bin/env bash
set -e
systemctl restart imobiliare-web
sleep 2
echo "--- stats:"; curl -s -m 5 http://127.0.0.1:8085/api/stats; echo
/opt/imobiliare/venv/bin/python /tmp/mk_tmp_listing.py
echo "--- listings?deal=rent:"; curl -s -m 5 "http://127.0.0.1:8085/api/listings?deal=rent" | head -c 600; echo
echo "--- detail:"; curl -s -m 5 http://127.0.0.1:8085/api/listing/1000000 -o /dev/null -w "not_found_status=%{http_code}\n" || true
ID=$(/opt/imobiliare/venv/bin/python -c "import sqlite3;print(sqlite3.connect('/opt/imobiliare/data/imobiliare.db').execute(\"select max(id) from listings\").fetchone()[0])")
echo "--- detail id=$ID:"; curl -s -m 5 http://127.0.0.1:8085/api/listing/$ID | head -c 600; echo
echo "--- contact without auth (expect 401):"; curl -s -m 5 -X POST http://127.0.0.1:8085/api/listing/$ID/contact; echo
echo "--- frontend served:"; curl -s -m 5 http://127.0.0.1:8085/ | head -c 120; echo
echo "--- restart bot:"; systemctl restart imobiliare; sleep 3
systemctl is-active imobiliare imobiliare-web
journalctl -u imobiliare -n 2 --no-pager | tail -2
echo "--- cleanup temp listing"
/opt/imobiliare/venv/bin/python -c "import sqlite3;db=sqlite3.connect('/opt/imobiliare/data/imobiliare.db');db.execute('delete from listings where id=?',($ID,));db.execute(\"delete from events where listing_id=$ID\");db.commit();print('cleaned')"
