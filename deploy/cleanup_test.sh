#!/usr/bin/env bash
set -e
/opt/imobiliare/venv/bin/python - <<'PYEOF'
import sqlite3
db = sqlite3.connect('/opt/imobiliare/data/imobiliare.db')
n2 = db.execute("delete from events where listing_id in (select id from listings where description like '%ТЕХНИЧЕСКИЙ ТЕСТ%')").rowcount
n1 = db.execute("delete from listings where description like '%ТЕХНИЧЕСКИЙ ТЕСТ%'").rowcount
db.execute("delete from events where name='channel_post'")
db.commit()
print('listings cleaned:', n1, '| events cleaned:', n2)
PYEOF
