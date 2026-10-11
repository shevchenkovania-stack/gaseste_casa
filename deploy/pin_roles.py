#!/usr/bin/env python3
"""Explain the three surfaces in the channel so users stop getting lost:
set a channel description + a pinned navigation post (bot = tool, channel = feed,
mini app = showcase). Idempotent for the description; the navigation post is added once.

Run on prod from /opt/imobiliare/bot:  /opt/imobiliare/venv/bin/python pin_roles.py
One-shot: re-running posts the navigation message again - do it only when the text changes.
"""
import asyncio
import sys

from aiogram import Bot

import config

DESCRIPTION = (
    "Găsește Casa — все новые объекты Кишинёва: аренда и продажа. Подать объявление: "
) + config.BOT_URL

PINNED = (
    "\U0001F4CC <b>Găsește Casa</b> — в этом канале появляются все новые объекты доски "
    "(квартиры и дома Кишинёва, аренда и продажа). Чтобы не путаться, где что:\n\n"
    "• <b>Канал</b> (вы здесь) — лента новинок. Понравилась карточка → жмите «Открыть» → "
    "контакт на карточке, договариваетесь напрямую.\n"
    f"• <b>Бот</b> <a href=\"{config.BOT_URL}\">gaseste_casa_bot</a> — инструмент: поиск по "
    "фильтрам, <b>подать своё объявление</b> (бесплатно, 2 минуты), поднятие в топ.\n"
    "• <b>Доска</b> — красивая витрина всех объявлений как на сайте: открывается кнопкой "
    "«\U0001F5FA\uFE0F Открыть приложение» в боте.\n\n"
    "Комиссии нет ни с кого: размещают и хозяева, и агенты — контакт всегда на карточке."
)


async def main() -> None:
    bot = Bot(token=config.BOT_TOKEN)
    await bot.set_chat_description(config.CHANNEL_ID, description=DESCRIPTION[:255])

    pinned = await bot.send_message(config.CHANNEL_ID, PINNED, parse_mode="HTML")
    await bot.pin_chat_message(config.CHANNEL_ID, pinned.message_id, disable_notification=True)
    print("✅ ROLES PINNED, message id", pinned.message_id)
    sys.stdout.flush()
    import os
    os._exit(0)  # old aiogram session.close() can hang; work is committed


asyncio.run(main())
