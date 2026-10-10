#!/bin/bash
# Token comes from the server .env - never hardcode it.
T=$(grep -E '^BOT_TOKEN=' /opt/imobiliare/bot/.env | cut -d= -f2-)
API="https://api.telegram.org/bot$T"

curl -s "$API/setMyName" --data-urlencode 'name=Găsește Casa | Аренда Кишинёв' >/dev/null
curl -s "$API/setMyShortDescription" --data-urlencode 'short_description=Аренда и продажа жилья в Кишинёве. Объявления бесплатно. Boost в топ за Stars.' >/dev/null

DESC=$(printf 'Găsește Casa — бот для аренды и продажи недвижимости в Кишинёве и пригородах.\n\n• Поиск квартир и домов по району, комнатам и цене\n• Разместить объявление — бесплатно\n• Контакт владельца напрямую, без комиссий\n• Boost за Telegram Stars — поднять объявление в топ\n\nНажми /start чтобы начать')
curl -s "$API/setMyDescription" --data-urlencode "description=$DESC" >/dev/null

echo '--- CHECK ---'
curl -s "$API/getMyName"; echo
curl -s "$API/getMyShortDescription"; echo
curl -s "$API/getMyDescription"; echo
