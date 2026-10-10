"""Create one DEMO listing owned by the admin and send him the real Boost offer.

Purpose: let the owner of the bot press the pay button once and verify the whole
Telegram Stars chain (invoice -> successful_payment -> boost -> admin report).
The demo listing is NOT posted to the public channel and is clearly marked.

Run: cd /opt/imobiliare/bot && /opt/imobiliare/venv/bin/python /tmp/make_demo.py
"""
import asyncio
import sys

sys.path.insert(0, "/opt/imobiliare/bot")

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

import config
import db
import keyboards

ADMIN_TG = config.ADMIN_IDS[0]


async def main() -> None:
    await db.init_db()
    bot = Bot(config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    conn = db._db()

    cur = await conn.execute("SELECT * FROM users WHERE tg_id = ?", (ADMIN_TG,))
    owner = await cur.fetchone()
    if not owner:
        sys.exit("admin is not a bot user yet - press /start in the bot first")

    # drop previous demos so the board doesn't fill with test cards
    await conn.execute("DELETE FROM events WHERE listing_id IN "
                       "(SELECT id FROM listings WHERE description LIKE '%ДЕМО%')")
    await conn.execute("DELETE FROM listings WHERE description LIKE '%ДЕМО%'")
    await conn.commit()

    listing_id = await db.create_listing(
        user_id=owner["id"], deal="rent", ptype="apartment", rooms=2, price=450, currency="EUR",
        district="Центр", area=54.0, floor=3, floors=9, phone="+371 79 000 000",
        description=("ДЕМО · тестовая карточка (не публикуется в канал). "
                     "Нужна только для проверки оплаты Boost."),
    )
    await conn.execute("UPDATE listings SET status='active' WHERE id=?", (listing_id,))
    await conn.commit()

    text = (
        f"\U0001F680 <b>Boost объявления #{listing_id}</b> (ДЕМО)\n\n"
        "Это тестовая карточка: нажми кнопку ниже и проверь кассу — оплату "
        "Telegram Stars, начисление Boost и отчёт себе как админу.\n\n"
        f"Цена: <b>{config.BOOST_STARS} Stars</b> \u2B50 (около 12 леев).\n"
        "Отмену и возврат \u2014 через поддержку Telegram Stars."
    )
    await bot.send_message(ADMIN_TG, text,
                           reply_markup=keyboards.boost_kb(listing_id, config.BOOST_STARS, config.BOOST_DAYS))
    print("demo listing:", listing_id, "| offer sent to", ADMIN_TG)

    await db.close_db()
    await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
