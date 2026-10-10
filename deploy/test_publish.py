"""E2E publish test with self-made dummy listing. Creates listing -> runs the real
production code path (publish.publish_listing). Cleanup: delete DB row by printed id +
delete the channel post manually (owner can).
Run on server: cd /opt/imobiliare/bot && /opt/imobiliare/venv/bin/python /tmp/test_publish.py
"""
import asyncio
import re
import sys

sys.path.insert(0, "/opt/imobiliare/bot")

txt = open("/opt/imobiliare/bot/.env").read()
token = re.search(r"^BOT_TOKEN=(\S+)", txt, re.M).group(1)

from aiogram import Bot

import db
import publish


async def main() -> None:
    await db.init_db()
    bot = Bot(token=token)

    listing_id = await db.create_listing(
        user_id=1, deal="rent", ptype="apartment", rooms=2, price=580, currency="EUR",
        district="Центр", area=55.0, floor=4, floors=9, phone="+37179999999",
        description="ТЕХНИЧЕСКИЙ ТЕСТ автопостинга (не реальное объявление). Будет удалён.",
        photos=[],
    )
    await db.set_listing_status(listing_id, "active")
    row = await db.get_listing(listing_id)
    await db.log_event("moderation_approve", listing_id=listing_id)
    await publish.publish_listing(bot, row)
    print("TEST_LISTING_ID", listing_id)
    await db.close_db()
    await bot.session.close()


asyncio.run(main())
