#!/usr/bin/env bash
# Turn this VPS into a public HTTPS host: nginx + Let's Encrypt in front of the Mini App.
# One HTTPS host unblocks two things at once: the Telegram Mini App (WEBAPP_URL) and the
# Lemon Squeezy payment webhook (the card rail cannot credit a Boost without it).
#
# Prerequisite (human): an A record for the domain pointing at this server's IP.
# Run: scp deploy/apply_https.sh root@SERVER:/tmp/ &&
#      ssh root@SERVER "sed -i 's/\r$//' /tmp/apply_https.sh && bash /tmp/apply_https.sh imobil.example.md"
set -e
DOMAIN="${1:?usage: apply_https.sh <domain-with-A-record>}"
EMAIL="${2:-admin@$DOMAIN}"
ENV=/opt/imobiliare/bot/.env

echo "=== packages ==="
export DEBIAN_FRONTEND=noninteractive
command -v nginx   >/dev/null || apt-get install -y -q nginx
command -v certbot >/dev/null || apt-get install -y -q certbot python3-certbot-nginx

echo "=== nginx site for $DOMAIN ==="
cat > /etc/nginx/sites-available/chirie <<EOF
server {
    listen 80;
    server_name ${DOMAIN};

    location /photos/ {
        alias /opt/imobiliare/data/photos/;
        expires 7d;
    }

    # provider webhooks are small JSON POSTs, no buffering tricks needed
    location / {
        proxy_pass http://127.0.0.1:8085;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
ln -sf /etc/nginx/sites-available/chirie /etc/nginx/sites-enabled/chirie
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl enable --now nginx
systemctl reload nginx

echo "=== firewall ==="
ufw allow 'Nginx Full' >/dev/null
ufw status | grep -E 'Nginx|80|443' || true

echo "=== certificate ==="
certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "$EMAIL" --redirect --keep-until-expiring

echo "=== reachable from the internet? ==="
curl -sS --max-time 15 "https://${DOMAIN}/api/stats"; echo
# 401 here means: public, TLS valid, route live, signature enforced
curl -sS -o /dev/null -w 'POST /webhook/lemonsqueezy -> %{http_code}\n' \
  -X POST -H 'Content-Type: application/json' -d '{}' "https://${DOMAIN}/webhook/lemonsqueezy"

echo "=== WEBAPP_URL ==="
if grep -q '^WEBAPP_URL=' "$ENV"; then
  sed -i "s|^WEBAPP_URL=.*|WEBAPP_URL=https://${DOMAIN}|" "$ENV"
else
  echo "WEBAPP_URL=https://${DOMAIN}" >> "$ENV"
fi
systemctl restart imobiliare
sleep 3
systemctl is-active imobiliare imobiliare-web nginx

cat <<EOF

DONE. Two things to register in Lemon Squeezy (Settings -> Webhooks -> New):
  Callback URL : https://${DOMAIN}/webhook/lemonsqueezy
  Events       : order_created, order_processed, order_refunded
  Signing secret: the same string you put into LS_WEBHOOK_SECRET in $ENV
Mini App button in the bot is live now (WEBAPP_URL=https://${DOMAIN}).
EOF
