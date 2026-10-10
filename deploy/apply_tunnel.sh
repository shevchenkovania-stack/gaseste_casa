#!/usr/bin/env bash
# Temporary public HTTPS for the card rail: a FREE Cloudflare quick tunnel in front of the Mini App.
# No domain, no certificate, no opened ports. The price: the URL is random and changes on every
# restart of the tunnel, so after every restart the webhook address must be re-saved in Lemon Squeezy.
# When a real domain exists, use deploy/apply_https.sh instead and disable this unit.
#
# Run: scp deploy/apply_tunnel.sh root@SERVER:/tmp/ && ssh root@SERVER "sed -i 's/\r$//' /tmp/apply_tunnel.sh && bash /tmp/apply_tunnel.sh"
# Safe to run repeatedly: it only re-reads the current URL and re-patches .env.
set -e
ENV=/opt/imobiliare/bot/.env
BIN=/usr/local/bin/cloudflared
UNIT=/etc/systemd/system/cloudflared-tunnel.service

echo "=== 1. binary ==="
if [ ! -x "$BIN" ]; then
  curl -fsSL -o /tmp/cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
  install -m 755 /tmp/cloudflared "$BIN"
fi
"$BIN" --version

echo "=== 2. systemd unit (tunnel -> 127.0.0.1:8085, survives reboots) ==="
cat > "$UNIT" <<'UNIT_EOF'
[Unit]
Description=Cloudflare quick tunnel for gaseste_casa (Mini App + Lemon Squeezy webhook)
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/local/bin/cloudflared tunnel --url http://127.0.0.1:8085 --no-autoupdate
Restart=always
RestartSec=5
# Quick tunnels need no credentials and no account: this unit only ever reads the URL from its log.

[Install]
WantedBy=multi-user.target
UNIT_EOF
systemctl daemon-reload
systemctl enable --now cloudflared-tunnel
sleep 10

echo "=== 3. the public URL (from the tunnel log) ==="
URL=$(journalctl -u cloudflared-tunnel --no-pager -o cat | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -1)
[ -n "$URL" ] || { echo "URL not in the log yet, wait 15s and run: journalctl -u cloudflared-tunnel -n 50 --no-pager"; exit 1; }
echo "URL=$URL"

echo "=== 4. write it into the bot config and restart ==="
if grep -q '^WEBAPP_URL=' "$ENV"; then
  sed -i "s|^WEBAPP_URL=.*|WEBAPP_URL=$URL|" "$ENV"
else
  echo "WEBAPP_URL=$URL" >> "$ENV"
fi
grep -q '^LS_WEBHOOK_SECRET=' "$ENV" || echo "LS_WEBHOOK_SECRET=" >> "$ENV"
systemctl restart imobiliare imobiliare-web
sleep 3
systemctl is-active imobiliare imobiliare-web cloudflared-tunnel

echo "=== 5. check the tunnel really serves the app and the webhook ==="
curl -s --max-time 20 -o /dev/null -w "GET  $URL/api/stats -> %{http_code}\n" "$URL/api/stats"
curl -s --max-time 20 -o /dev/null -w "POST $URL/webhook/lemonsqueezy -> %{http_code}\n" \
  -X POST -H 'Content-Type: application/json' -d '{}' "$URL/webhook/lemonsqueezy"
echo "(401 on the webhook = it is reachable from the internet and the signature is enforced)"

echo
echo "==================== ЧТО ТЕПЕРЬ РУКАМИ ===================="
echo "1) Регистрируем вебхук LS в LS самим (нужны LS_API_KEY и LS_STORE_ID в .env):"
echo "   /opt/imobiliare/venv/bin/python /tmp/register_ls_webhook.py"
echo "   (он же создаст тестовый и боевой вебхук, сгенерит секрет, впишет его в .env и рестартует сервисы)"
echo
echo "2) После ЛЮБОЙ перезагрузки сервера или туннеля адрес меняется. Тогда две команды:"
echo "   bash /tmp/apply_tunnel.sh          # новый адрес в WEBAPP_URL"
echo "   /opt/imobiliare/venv/bin/python /tmp/register_ls_webhook.py   # пересоздать вебхук на новый адрес"
echo "Пока домена нет, старый адрес в LS превращается в мёртвой: LS будет слать заказы в никуда,"
echo "а сторож «Касса молчит» (§9) об этом напишет. Постоянный домен убирает эту проблему совсем."
echo "==========================================================="
