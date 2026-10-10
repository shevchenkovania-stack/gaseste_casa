#!/bin/bash
T="REPLACE_WITH_BOT_TOKEN_FROM_ENV"
API="https://api.telegram.org/bot$T"
curl -s -F 'photo={"type":"static","photo":"attach://p"}' -F 'p=@/root/avatar.png' "$API/setMyProfilePhoto"
echo
