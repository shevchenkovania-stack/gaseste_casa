"""Set the brand logo everywhere: bot profile photo + public channel photo.

Run on prod: cd /opt/imobiliare/bot && /opt/imobiliare/venv/bin/python set_logo.py /tmp/logo.png
Token and CHANNEL_ID come from the service .env via config - nothing is hardcoded.
"""
import asyncio
import sys

sys.path.insert(0, "/opt/imobiliare/bot")

import aiohttp

import config

PATH = sys.argv[1] if len(sys.argv) > 1 else "/tmp/logo.png"


async def post(sess: aiohttp.ClientSession, method: str, fields: dict) -> None:
    data = aiohttp.FormData()
    for name, value in fields.items():
        if isinstance(value, bytes):
            data.add_field(name, value, filename="logo.png", content_type="image/png")
        else:
            data.add_field(name, value)
    url = f"https://api.telegram.org/bot{config.BOT_TOKEN}/{method}"
    async with sess.post(url, data=data) as resp:
        print(method, resp.status, await resp.text())


async def main() -> None:
    blob = open(PATH, "rb").read()
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as sess:
        # setMyProfilePhoto does not accept a bare multipart part named "photo" (Bot API quirk,
        # already proven by set_avatar.sh): the file goes under an arbitrary name and "photo"
        # references it via attach://. setChatPhoto happily takes the plain part.
        data = aiohttp.FormData()
        data.add_field("photo", '{"type":"static","photo":"attach://p"}')
        data.add_field("p", blob, filename="logo.png", content_type="image/png")
        url = f"https://api.telegram.org/bot{config.BOT_TOKEN}/setMyProfilePhoto"
        async with sess.post(url, data=data) as resp:
            print("setMyProfilePhoto", resp.status, await resp.text())
        if config.CHANNEL_ID:
            await post(sess, "setChatPhoto", {"chat_id": config.CHANNEL_ID, "photo": blob})
        else:
            print("CHANNEL_ID not set - channel photo skipped")


asyncio.run(main())
