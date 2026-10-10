#!/usr/bin/env bash
# Is our public front door alive? One command, run it after every tunnel restart / reboot / deploy.
# It answers the only question that matters for the card rail: can Lemon Squeezy still reach us,
# and does the Mini App still load for a buyer. Reads the URL from .env, so it never lies.
#
# Run: bash /tmp/check_public.sh
set -e
ENV=/opt/imobiliare/bot/.env
URL=$(grep '^WEBAPP_URL=' "$ENV" | cut -d= -f2- || true)
echo "WEBAPP_URL = ${URL:-"(пусто)"}"

echo "=== процессы ==="
for s in imobiliare imobiliare-web cloudflared-tunnel; do
  printf '%-20s %s\n' "$s" "$(systemctl is-active "$s" 2>/dev/null || true)"
done

if [ -z "$URL" ]; then
  echo "Адреса нет — проверять снаружи нечего. Сначала bash /tmp/apply_tunnel.sh"
  exit 0
fi

echo "=== снаружи, через публичный адрес ==="
code() { curl -s -o /dev/null -m 25 -w '%{http_code}' "$@"; }
echo "GET  /            -> $(code "$URL/")                  (200 = витрина жива)"
echo "GET  /api/stats   -> $(code "$URL/api/stats")         (200 = aiohttp отвечает)"
echo "POST /webhook/..  -> $(code -X POST -H 'Content-Type: application/json' -d '{}' "$URL/webhook/lemonsqueezy")         (401 = вебхук доступен и требует подпись)"
echo "GET  /photos/     -> $(code "$URL/photos/")          (403/200/404 = фото отдаются наружу)"
echo "фактический ответ /api/stats: $(curl -s -m 25 "$URL/api/stats")"

echo "=== очередь карточных платежей ==="
DB=/opt/imobiliare/data/imobiliare.db
sqlite3 "$DB" "select 'card_orders: '||count(*)||' неначисленных: '||sum(applied=0) from card_orders;" 2>/dev/null || \
  echo "(sqlite3 CLI нет — см. /stats в боте: card_unapplied)"
sqlite3 "$DB" "select 'последние события: '||group_concat(name, ', ') from (select name from events order by created_at desc limit 8);" 2>/dev/null || true

echo
echo "Если POST /webhook даёт не 401:"
echo "  000  -> туннель умер или адрес сменился: bash /tmp/apply_tunnel.sh"
echo "  404  -> веб-процесс не тот: systemctl restart imobiliare-web"
echo "  200/403 на GET -> всё хорошо, проблема на стороне LS (вебхук указывает на старый адрес):"
echo "         /opt/imobiliare/venv/bin/python /tmp/register_ls_webhook.py"
