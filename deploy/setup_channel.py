"""Attach the public channel to ChirieBot: verify access, write .env, post a test message.
Run on server: /opt/imobiliare/venv/bin/python /tmp/setup_channel.py @gaseste_casa
"""
import json
import re
import sys
import urllib.parse
import urllib.request

ENV = "/opt/imobiliare/bot/.env"
chat = sys.argv[1] if len(sys.argv) > 1 else "@gaseste_casa"

txt = open(ENV).read()
token = re.search(r"^BOT_TOKEN=(\S+)", txt, re.M).group(1)


def api(method, **kw):
    data = urllib.parse.urlencode(kw).encode()
    resp = urllib.request.urlopen(f"https://api.telegram.org/bot{token}/{method}", data)
    return json.loads(resp.read())


me = api("getMe")["result"]
print("bot:", me["username"])

try:
    info = api("getChat", chat_id=chat)
    print("chat:", json.dumps(info, ensure_ascii=False)[:300])
    if not info.get("ok"):
        sys.exit("chat not found")
    member = api("getChatMember", chat_id=chat, user_id=me["id"])["result"]
    print("bot status in chat:", member["status"], "| can_post:", member.get("can_post"))
    if member["status"] == "left":
        sys.exit("bot is NOT admin of this channel")

    # write CHANNEL_ID into .env
    if re.search(r"^CHANNEL_ID=", txt, re.M):
        txt = re.sub(r"^CHANNEL_ID=.*$", f"CHANNEL_ID={chat}", txt, flags=re.M)
    else:
        txt = txt.rstrip("\n") + f"\nCHANNEL_ID={chat}\n"
    if not re.search(r"^WEBAPP_URL=", txt, re.M):
        txt = txt.rstrip("\n") + "\nWEBAPP_URL=\n"
    open(ENV, "w").write(txt)
    print(".env updated: CHANNEL_ID=", chat)

    r = api("sendMessage", chat_id=chat, parse_mode="HTML",
            text=("✅ <b>Канал подключён к боту!</b>\n\n"
                  "Здесь будут автоматически появляться новые квартиры "
                  "Кишинёва — бесплатно и без пауз.\n"
                  f"Разместить своё объявление: t.me/{me['username']}"))
    print("test post ok:", r.get("ok"))
except urllib.error.HTTPError as e:
    print("API error:", e.read().decode()[:300])
    sys.exit(1)
