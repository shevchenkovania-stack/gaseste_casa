#!/usr/bin/env python3
"""Unify the visible brand name across Telegram: channel title + bot display name.

Root cause this fixes: the channel was created on day one as "Квартиры в Кишинёве | Chirie"
(pre-brand) and the bot name said "Аренда" (now wrong - the board has sales too).
One title everywhere; internal codename "chiriebot" stays in logs only.

Run on prod from /opt/imobiliare/bot:  /opt/imobiliare/venv/bin/python rename.py
Idempotent: prints current names, sets the new ones, verifies via get_chat/get_me.
"""
import asyncio

from aiogram import Bot

import config

TITLE = "Găsește Casa · Недвижимость Кишинёва"


async def main() -> None:
    bot = Bot(token=config.BOT_TOKEN)
    me = await bot.get_me()
    print("bot name was:", me.first_name)
    chat = await bot.get_chat(config.CHANNEL_ID)
    print("channel title was:", chat.title)

    await bot.set_my_name(name=TITLE, language_code="")
    await bot.set_my_name(name=TITLE, language_code="ru")
    await bot.set_chat_title(config.CHANNEL_ID, title=TITLE)

    me = await bot.get_me()
    chat = await bot.get_chat(config.CHANNEL_ID)
    print("bot name now: ", me.first_name)
    print("channel now:  ", chat.title)
    print("✅ RENAMED OK" if me.first_name == TITLE and chat.title == TITLE else "⚠️ check failed")


asyncio.run(main())
