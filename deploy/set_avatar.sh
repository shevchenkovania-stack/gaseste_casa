#!/bin/bash
# Token comes from the server .env - never hardcode it.
T=$(grep -E '^BOT_TOKEN=' /opt/imobiliare/bot/.env | cut -d= -f2-)
API="https://api.telegram.org/bot$T"
curl -s -F 'photo={"type":"static","photo":"attach://p"}' -F 'p=@/root/avatar.png' "$API/setMyProfilePhoto"
echo
