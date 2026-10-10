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
set_key() {
  old=$(grep "^$1=" "$ENV" | head -1 | cut -d= -f2-)
  [ "$old" = "$2" ] && { echo "$1 уже = $2"; return; }
  if grep -q "^$1=" "$ENV"; then sed -i "s|^$1=.*|$1=$2|" "$ENV"; else echo "$1=$2" >> "$ENV"; fi
  echo "$1: '$old' -> '$2'"
}
add_key BOOST_MDL 100
add_key PAY_INFO ""
add_key PAY_PHONE ""
add_key PAY_NAME ""
# Price parity: 50 Stars is ~$0.65 of reward against a $5.00 card rail, so a buyer could always
# pick the loophole. 400 Stars ~= $5.20. .env stays the source of truth: change it there if you
# disagree, this line only fixes the known hole.
set_key BOOST_STARS 400
grep -E '^(BOOST_STARS|BOOST_DAYS|BOOST_MDL|PAY_PHONE|PAY_NAME|PAY_INFO|CHANNEL_ID|BOT_USERNAME)=' "$ENV"

echo "=== restart ==="
systemctl restart imobiliare
sleep 3
systemctl is-active imobiliare imobiliare-web

echo "=== wiring ==="
/opt/imobiliare/venv/bin/python - <<'PYEOF'
import sys
sys.path.insert(0, "/opt/imobiliare/bot")
import config, keyboards
from handlers import boost, admin
print("BOOST_MDL =", config.BOOST_MDL, "| PAY_PHONE set:", bool(config.PAY_PHONE),
      "| PAY_INFO set:", bool(config.PAY_INFO))
print("rails:", keyboards.rails_line())
print("кнопка:", keyboards.transfer_button(), "| Stars:", config.BOOST_STARS)

# the copy block is what the buyer taps to copy: order and escaping are money-critical
config.BOOST_MDL = 100
config.PAY_PHONE = "+37379123456"
config.PAY_NAME = "Ion C"
config.PAY_INFO = "maib"
assert keyboards.pay_lines(12) == ["+37379123456", "Ion C", "maib", "Boost #12"], keyboards.pay_lines(12)
assert keyboards.pay_block(12) == "<code>+37379123456\nIon C\nmaib\nBoost #12</code>"
pitch = keyboards.manual_pitch(12)
for needle in ("MIA", "+37379123456", "Ion C", "Boost #12", "100 MDL"):
    assert needle in pitch, needle
config.PAY_PHONE = ""
assert "MIA" not in keyboards.manual_pitch(12), "without a phone there is no MIA claim"
config.PAY_INFO = "карта <5199> & co"
assert "&lt;5199&gt; &amp; co" in keyboards.manual_pitch(12), "PAY_INFO must be HTML-escaped"
print("pitch: OK (MIA-ветка и fallback ветка, экранирование работает)")

config.PAY_PHONE = "+37379123456"
config.PAY_INFO = "карта 5199 0000 0000 0000, maib"
print("пример покупателю:")
print(keyboards.manual_pitch(12))
print("boost callbacks:", [getattr(getattr(h, "callback", h), "__name__", str(h))
                           for h in boost.router.callback_query.handlers])
print("admin callbacks:", [getattr(getattr(h, "callback", h), "__name__", str(h))
                           for h in admin.router.callback_query.handlers])
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
