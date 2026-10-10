#!/usr/bin/env bash
T=$(grep '^BOT_TOKEN=' /opt/imobiliare/bot/.env | cut -d= -f2)
curl -s "https://api.telegram.org/bot${T}/getMe" | /opt/imobiliare/venv/bin/python -c 'import json,sys; r=json.load(sys.stdin)["result"]; print("BOT_USERNAME", r["username"]); print("BOT_NAME", r["first_name"])'
