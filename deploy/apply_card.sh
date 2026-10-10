#!/usr/bin/env bash
# Apply the card rail (Lemon Squeezy): compile, env keys, restart both services, verify wiring.
# Run: scp deploy/apply_card.sh root@SERVER:/tmp/ && ssh root@SERVER "sed -i 's/\r$//' /tmp/apply_card.sh && bash /tmp/apply_card.sh"
set -e
cd /opt/imobiliare/bot
ENV=/opt/imobiliare/bot/.env

echo "=== compile ==="
/opt/imobiliare/venv/bin/python -m py_compile \
  config.py constants.py db.py keyboards.py scheduler.py publish.py render.py main.py lemon.py \
  handlers/*.py webapp/app.py
echo "compile OK"

echo "=== env ==="
add_key() { grep -q "^$1=" "$ENV" || echo "$1=$2" >> "$ENV"; }
add_key LS_API_KEY ""
add_key LS_STORE_ID ""
add_key LS_VARIANT_ID ""
add_key LS_WEBHOOK_SECRET ""
add_key CARD_PRICE_CENTS 500
grep -cE '^(LS_API_KEY|LS_STORE_ID|LS_VARIANT_ID|LS_WEBHOOK_SECRET|CARD_PRICE_CENTS)=' "$ENV"

echo "=== restart (bot first: it owns the schema) ==="
systemctl restart imobiliare
sleep 2
systemctl restart imobiliare-web
sleep 3
systemctl is-active imobiliare imobiliare-web

echo "=== wiring ==="
/opt/imobiliare/venv/bin/python - <<'PYEOF'
import sys
sys.path.insert(0, "/opt/imobiliare/bot")
import config, db, keyboards, lemon
from handlers import boost

def names(handlers):
    return [getattr(getattr(h, "callback", h), "__name__", str(h)) for h in handlers]

print("CARD_ENABLED:", config.CARD_ENABLED, "| price:", keyboards.usd(config.CARD_PRICE_CENTS),
      "| webhook secret set:", bool(config.LS_WEBHOOK_SECRET))
print("boost callback handlers:", names(boost.router.callback_query.handlers))
print("rails line:", keyboards.rails_line())
print("db has store_card_order/ensure_schema:",
      hasattr(db, "store_card_order"), hasattr(db, "ensure_schema"))
PYEOF

echo "=== webhook endpoint (401 = route live and signature enforced) ==="
curl -s -o /dev/null -w 'POST /webhook/lemonsqueezy -> %{http_code}\n' \
  -X POST -H 'Content-Type: application/json' -d '{}' http://127.0.0.1:8085/webhook/lemonsqueezy
curl -s --max-time 5 http://127.0.0.1:8085/api/stats; echo

echo "=== schema ==="
/opt/imobiliare/venv/bin/python - <<'PYEOF'
import sqlite3
d = sqlite3.connect('/opt/imobiliare/data/imobiliare.db')
print('card_orders cols:', [r[1] for r in d.execute('PRAGMA table_info(card_orders)')])
print('payments cols:', [r[1] for r in d.execute('PRAGMA table_info(payments)')])
PYEOF

echo "=== log ==="
journalctl -u imobiliare -n 5 --no-pager -o cat
journalctl -u imobiliare-web -n 5 --no-pager -o cat
