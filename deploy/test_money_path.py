"""Money-path smoke test, run on the server.

Creates a private TEST listing owned by the admin, ages it 3 days, then runs the real
production nudge job so the admin receives a DM with a working "Оплатить N Stars"
button. Nothing is posted to the public channel and the DB is left clean.

Run: cd /opt/imobiliare/bot && /opt/imobiliare/venv/bin/python /tmp/test_money_path.py
"""
import asyncio
import sys

sys.path.insert(0, "/opt/imobiliare/bot")

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

import config
import db
import scheduler

ADMIN_TG = config.ADMIN_IDS[0]


async def main() -> None:
    if not config.BOT_TOKEN:
        sys.exit("BOT_TOKEN missing")
    await db.init_db()
    bot = Bot(config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    conn = db._db()

    cur = await conn.execute("SELECT * FROM users WHERE tg_id = ?", (ADMIN_TG,))
    owner = await cur.fetchone()
    if not owner:
        sys.exit(f"admin tg_id {ADMIN_TG} is not a user - open the bot and press /start first")

    listing_id = await db.create_listing(
        user_id=owner["id"], deal="rent", ptype="apartment", rooms=2, price=1, currency="EUR",
        district="Технический тест", area=50.0, floor=1, floors=5, phone="",
        description="ТЕХНИЧЕСКИЙ ТЕСТ денежного пути. Не трогать, будет удалён.",
    )
    # active + aged, so the real nudge query picks it up
    await conn.execute("UPDATE listings SET status='active', created_at=datetime('now','-3 days') WHERE id=?",
                       (listing_id,))
    await conn.commit()

    picked = await db.listings_to_nudge(config.NUDGE_AFTER_DAYS, config.NUDGE_COOLDOWN_DAYS)
    print("picked by nudge query:", [r["id"] for r in picked])

    sent = await scheduler.nudge_unboosted(bot)
    print("nudge messages sent:", sent)

    await conn.execute("DELETE FROM events WHERE listing_id = ?", (listing_id,))
    await conn.execute("DELETE FROM listings WHERE id = ?", (listing_id,))
    await conn.commit()
    left = await conn.execute("SELECT COUNT(*) c FROM listings WHERE id = ?", (listing_id,))
    print("cleaned, listing rows left:", (await left.fetchone())["c"])

    await db.close_db()
    await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
