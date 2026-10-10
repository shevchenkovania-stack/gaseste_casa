"""Post (and pin) the forwardable "about the service" card in the public channel.

Run: cd /opt/imobiliare/bot && /opt/imobiliare/venv/bin/python /tmp/post_promo.py
"""
import asyncio
import sys

sys.path.insert(0, "/opt/imobiliare/bot")

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import config
import keyboards

# The Boost line comes from keyboards.boost_pitch() — the single source of price copy. A pinned
# channel post that hardcodes "50 Stars" is the kind of lie a client finds on the first tap.
TEXT = (
    "\U0001F3E0 <b>Găsește Casa | Chirie</b> — квартиры и дома в Кишинёве\n\n"
    "Сюда бот сам выкладывает каждое одобренное объявление: цена, район, площадь, "
    "фото и контакт владельца.\n"
    "Размещение <b>бесплатное</b>.\n\n"
    "<b>Как сдать или продать за 2 минуты:</b>\n"
    "1\uFE0F\u20E3 открой бота \u2192 «\u2795 Разместить объект»\n"
    "2\uFE0F\u20E3 район, цена, фото, контакт\n"
    "3\uFE0F\u20E3 короткая модерация \u2014 и объявление уже здесь\n\n"
    f"{keyboards.boost_pitch()}\n\n"
    "\U0001F4E3 Перешли этот пост тому, кто сдаёт квартиру."
)

KB = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="\u2795 Разместить своё объявление", url=config.BOT_URL)],
    [InlineKeyboardButton(text="\U0001F50D Искать объект", url=f"{config.BOT_URL}?start=promo")],
])


async def main() -> None:
    if not config.CHANNEL_ID:
        sys.exit("CHANNEL_ID is not set")
    bot = Bot(config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    if len(sys.argv) > 1:  # edit the existing pinned card instead of posting a duplicate
        mid = int(sys.argv[1])
        await bot.edit_message_text(TEXT, chat_id=config.CHANNEL_ID, message_id=mid,
                                    reply_markup=KB)
        print("edited message_id:", mid)
        await bot.session.close()
        return
    msg = await bot.send_message(config.CHANNEL_ID, TEXT, reply_markup=KB)
    print("posted message_id:", msg.message_id)
    try:
        await bot.pin_chat_message(config.CHANNEL_ID, msg.message_id)
        print("pinned")
    except Exception as e:
        print("pin skipped:", e)
    await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
