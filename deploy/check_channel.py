"""Dump channel state: chat info, pinned, admins, recent photo."""
import asyncio
import json
import os
import sys

sys.path.insert(0, "/opt/imobiliare/bot")
import config
from aiogram import Bot


async def main():
    bot = Bot(token=config.BOT_TOKEN)
    cid = config.CHANNEL_ID
    chat = await bot.get_chat(cid)
    out = {
        "id": chat.id,
        "type": chat.type,
        "title": chat.title,
        "username": chat.username,
        "description": chat.description,
        "has_photo": chat.photo is not None,
        "photo_small": chat.photo.small_file_id if chat.photo else None,
        "photo_big": chat.photo.big_file_id if chat.photo else None,
        "members": await bot.get_chat_member_count(cid),
    }
    try:
        pin = await bot.get_chat_pinned_message(cid)
        out["pinned"] = {
            "message_id": pin.message_id,
            "text": (pin.text or "")[:500],
            "caption": (pin.caption or "")[:500] if pin.caption else None,
            "has_photo": bool(pin.photo),
            "reply_markup": str(pin.reply_markup)[:800] if pin.reply_markup else None,
        }
    except Exception as e:
        out["pinned"] = f"ERR {e}"
    try:
        admins = await bot.get_chat_administrators(cid)
        out["admins"] = [{"id": a.user.id, "uname": a.user.username, "bot": a.user.is_bot} for a in admins]
    except Exception as e:
        out["admins"] = f"ERR {e}"
    if chat.photo:
        f = await bot.get_file(chat.photo.big_file_id)
        await bot.download_file(f.file_path, "/tmp/channel_avatar.jpg")
        out["avatar_saved"] = "/tmp/channel_avatar.jpg"
    print(json.dumps(out, ensure_ascii=False, indent=2))
    await bot.session.close()


asyncio.run(main())
