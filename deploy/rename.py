#!/usr/bin/env python3
"""Give each Telegram surface a role-distinct name under one brand.

Why this exists: we had first collapsed bot + channel to the SAME name, which reads as two
identical rows in the chat list = the "хаос" the founder flagged. One brand prefix is right,
but the tail of the name must carry the ROLE so a person can tell them apart at a glance.
The word "бот" stays out of the display name (Telegram already labels it as a bot + shows
@gaseste_casa_bot); the tail is a discoverability keyword instead.

  Bot    -> Găsește Casa · Недвижимость Кишинёва   (the tool: search, submit, payment)
  Channel-> Găsește Casa · Лента объектов          (the feed: read-only)
  (Mini App <title> = "... · Доска объявлений" lives in webapp/static/index.html)

Run on prod from /opt/imobiliare/bot:  /opt/imobiliare/venv/bin/python rename.py
Idempotent: prints current names, sets the new ones, verifies via get_chat/get_me.
"""
import asyncio

from aiogram import Bot

import config

BOT_TITLE = "Găsește Casa · Недвижимость Кишинёва"
CHANNEL_TITLE = "Găsește Casa · Лента объектов"


async def main() -> None:
    bot = Bot(token=config.BOT_TOKEN)
    me = await bot.get_me()
    print("bot name was:", me.first_name)
    chat = await bot.get_chat(config.CHANNEL_ID)
    print("channel title was:", chat.title)

    await bot.set_my_name(name=BOT_TITLE, language_code="")
    await bot.set_my_name(name=BOT_TITLE, language_code="ru")
    await bot.set_chat_title(config.CHANNEL_ID, title=CHANNEL_TITLE)

    me = await bot.get_me()
    chat = await bot.get_chat(config.CHANNEL_ID)
    print("bot name now: ", me.first_name)
    print("channel now:  ", chat.title)
    ok = me.first_name == BOT_TITLE and chat.title == CHANNEL_TITLE
    print("✅ RENAMED OK" if ok else "⚠️ check failed")


asyncio.run(main())
