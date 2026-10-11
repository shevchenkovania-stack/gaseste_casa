#!/usr/bin/env bash
set -e
echo "=== services ==="
systemctl is-active imobiliare imobiliare-web
echo "=== db counts ==="
/opt/imobiliare/venv/bin/python - <<'PYEOF'
import sqlite3
d = sqlite3.connect('/opt/imobiliare/data/imobiliare.db')
for k in ('users', 'listings', 'boosts', 'payments', 'events', 'card_orders'):
    print(k, d.execute(f'select count(*) from {k}').fetchone()[0])
print('listing statuses:', d.execute("select status, count(*) from listings group by status").fetchall())
print('boost statuses:', d.execute("select status, count(*) from boosts group by status").fetchall())
print('payments:', d.execute("select currency, purpose, amount, is_test from payments").fetchall())
# the two numbers that mean "money is waiting for a human decision"
print('refunds:', d.execute("select count(*) from payments where refunded_at is not null").fetchone()[0])
print('manual waiting:', d.execute("select count(*) from boosts where status='manual_pending'").fetchone()[0])
print('events:', d.execute("select name, count(*) from events group by name").fetchall())
print('listings:', d.execute("select id, status, district, price, currency, boosted_until is not null from listings group by id order by id desc limit 10").fetchall())
PYEOF
echo "=== money config (effective) ==="
grep -E '^(CARD_PRICE_CENTS|BOOST_MDL|BOOST_STARS|BOOST_DAYS|PAY_PHONE|PAY_NAME|PAY_INFO|WEBAPP_URL|LS_STORE_ID|LS_API_KEY|LS_VARIANT_ID)=' /opt/imobiliare/bot/.env | sed -E 's/(KEY|SECRET)=.*/\1=***/'
echo "=== card rail enabled? ==="
cd /opt/imobiliare/bot && /opt/imobiliare/venv/bin/python -c "import config; print('CARD_ENABLED', config.CARD_ENABLED); print('MIA word', __import__('keyboards').transfer_word())" 2>&1 | tail -3
echo "=== money safety (backup + ssh) ==="
LAST=$(ls -1 /opt/imobiliare/data/backups/imobiliare-*.db 2>/dev/null | tail -1)
if [ -z "$LAST" ]; then echo "BACKUPS: none — run deploy/apply_backup.sh"; else
  echo "BACKUPS: $(ls -1 /opt/imobiliare/data/backups/imobiliare-*.db | wc -l) файлов, последний $LAST"
  /opt/imobiliare/venv/bin/python -c "import sqlite3,sys; print('integrity:', sqlite3.connect(sys.argv[1]).execute('pragma integrity_check').fetchone()[0])" "$LAST"
fi
fail2ban-client status sshd 2>&1 | tr -s ' \t' ' ' | grep -E 'Status|Failed|Banned' || echo "fail2ban: not active"
sshd -T 2>/dev/null | grep -E '^(permitrootlogin|passwordauthentication)' || true
echo "=== env keys ==="
grep -oE '^[A-Z_]+' /opt/imobiliare/bot/.env
echo "=== channel id ==="
grep '^CHANNEL_ID' /opt/imobiliare/bot/.env
echo "=== webapp stats ==="
curl -s --max-time 5 http://127.0.0.1:8085/api/stats
echo
echo "=== last bot log ==="
journalctl -u imobiliare -n 5 --no-pager -o cat
