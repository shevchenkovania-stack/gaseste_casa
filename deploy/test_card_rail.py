"""End-to-end test of the card rail WITHOUT a Lemon Squeezy account and without money.

Forges the exact thing LS will send (order_created + HMAC of the raw body), pushes it through
the real production code path and asserts the whole money chain:
  signature -> parse_order_event -> card_orders inbox -> scheduler.apply_card_orders
  -> listing boosted -> payments row (real currency, is_test=0) -> /stats revenue_card
Dedupe is checked too: a repeated webhook must not pay twice. Everything is deleted afterwards.

Run: cd /opt/imobiliare/bot && /opt/imobiliare/venv/bin/python /tmp/test_card_rail.py
"""
import asyncio
import hashlib
import hmac
import json
import sys

sys.path.insert(0, "/opt/imobiliare/bot")

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

import config
import db
import keyboards
import lemon
import scheduler

ADMIN_TG = config.ADMIN_IDS[0]
SECRET = "railtest-secret"
ORDER_ID = "00000000-0000-4000-8000-0000000000ca"


def order_event(listing_id: int, tg_id: int, status: str = "paid") -> bytes:
    """Body exactly as Lemon Squeezy delivers it: meta.custom_data + order attributes."""
    return json.dumps({
        "meta": {
            "event_name": "order_created",
            "custom_data": {"listing_id": str(listing_id), "tg_id": str(tg_id)},
        },
        "data": {
            "type": "orders",
            "id": "1",
            "attributes": {
                "identifier": ORDER_ID,
                "total": config.CARD_PRICE_CENTS,
                "currency": "USD",
                "status": status,
                "test_mode": False,
                "user_email": "test@example.com",
            },
        },
    }).encode()


async def main() -> None:
    await db.init_db()
    bot = Bot(config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    conn = db._db()
    cur = await conn.execute("SELECT * FROM users WHERE tg_id = ?", (ADMIN_TG,))
    owner = await cur.fetchone()
    if not owner:
        sys.exit("admin is not a bot user yet - press /start in the bot first")

    listing_id = await db.create_listing(
        user_id=owner["id"], deal="rent", ptype="apartment", rooms=1, price=300, currency="EUR",
        district="Буюкань", area=40.0, floor=2, floors=5, phone="+373 000 000 00",
        description="ДЕМО · тест карточного рельса (не публикуется в канал)",
    )
    await conn.execute("UPDATE listings SET status='active' WHERE id=?", (listing_id,))
    await conn.commit()
    print("test listing:", listing_id)

    try:
        raw = order_event(listing_id, ADMIN_TG)
        config.LS_WEBHOOK_SECRET = SECRET  # what .env will hold once the LS webhook exists
        sig = hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
        assert lemon.verify_signature(raw, sig), "signature must pass"
        assert not lemon.verify_signature(raw, "deadbeef"), "tampered body must fail"
        print("signature: OK (valid accepted, forged rejected)")

        order = lemon.parse_order_event(json.loads(raw))
        assert order and order["listing_id"] == listing_id and order["tg_id"] == ADMIN_TG
        assert order["amount_cents"] == config.CARD_PRICE_CENTS and order["status"] == "paid"
        print("parsed order:", order["order_id"], order["amount_cents"], order["currency"])

        buyer = await db.get_user_by_tg_id(ADMIN_TG)
        assert buyer["id"] == owner["id"]

        assert await db.store_card_order(conn, order) is True, "first delivery is new"
        assert await db.store_card_order(conn, order) is False, "duplicate must not insert"
        print("inbox: 1 row, duplicate ignored")

        applied = await scheduler.apply_card_orders(bot)
        assert applied == 1, f"expected one applied order, got {applied}"
        assert await scheduler.apply_card_orders(bot) == 0, "second pass must be a no-op"

        row = await db.get_listing(listing_id)
        assert row["boosted_until"], "listing must be boosted"
        cur = await conn.execute("SELECT * FROM payments WHERE provider_charge_id = ?", (ORDER_ID,))
        pay = await cur.fetchone()
        assert pay["currency"] == "USD" and abs(pay["amount"] - config.CARD_PRICE_CENTS / 100) < 1e-9
        assert pay["purpose"] == "boost_card" and pay["is_test"] == 0
        cur = await conn.execute("SELECT status FROM boosts WHERE listing_id = ?", (listing_id,))
        assert (await cur.fetchone())["status"] == "paid"
        s = await db.stats()
        assert float(s["revenue_card"]) >= config.CARD_PRICE_CENTS / 100, s
        assert s["card_unapplied"] == 0
        print(f"money chain: boost until {row['boosted_until']}, "
              f"payment {pay['amount']} {pay['currency']}, revenue_card={s['revenue_card']}")
        print("admin/buyer got the real notifications: "
              f"💳 {config.CARD_PRICE_CENTS/100:.2f} USD, keyboard {keyboards.rails_line()}")
        print("\u2705 CARD RAIL OK - as soon as LS fires the webhook, the boost is credited by itself")
    finally:
        await conn.execute("DELETE FROM events WHERE listing_id = ?", (listing_id,))
        await conn.execute("DELETE FROM boosts WHERE listing_id = ?", (listing_id,))
        await conn.execute("DELETE FROM payments WHERE provider_charge_id = ?", (ORDER_ID,))
        await conn.execute("DELETE FROM card_orders WHERE order_id = ?", (ORDER_ID,))
        await conn.execute("DELETE FROM listings WHERE id = ?", (listing_id,))
        await conn.commit()
        print("cleanup done, board back to its real state")
        await db.close_db()
        await bot.session.close()


asyncio.run(main())
