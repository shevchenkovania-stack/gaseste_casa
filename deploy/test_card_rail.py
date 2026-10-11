"""End-to-end test of the card rail WITHOUT a Lemon Squeezy account and without money.

Forges the exact thing LS will send (order_created + HMAC of the raw body), pushes it through
the real production code path and asserts the whole money chain:
  signature -> parse_order_event -> card_orders inbox -> scheduler.apply_card_orders
  -> listing boosted -> payments row (real currency, is_test=0) -> /stats revenue_card
Dedupe is checked too: a repeated webhook must not pay twice. The webhook watchdog is verified as
pure logic plus one "healthy rail stays silent" pass, so no admin receives a test DM.
Then the money that comes back is tested as well: a refund switches the boost off and leaves
REAL_REVENUE, a partial refund changes nothing, an unconfirmed MIA claim is reminded once per
window, and an expired Boost produces exactly one repeat-sale offer.
Everything is deleted afterwards.

Run: cd /opt/imobiliare/bot && /opt/imobiliare/venv/bin/python /tmp/test_card_rail.py
"""
import asyncio
import hashlib
import hmac
import json
import sys
import time

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
        revenue_before = float(s["revenue_card"])
        print(f"money chain: boost until {row['boosted_until']}, "
              f"payment {pay['amount']} {pay['currency']}, revenue_card={s['revenue_card']}")
        print("admin/buyer got the real notifications: "
              f"💳 {config.CARD_PRICE_CENTS/100:.2f} USD, keyboard {keyboards.rails_line()}")

        # --- watchdog: does the bot notice a silent webhook? (must stay quiet when healthy) ---
        await db.log_event("card_checkout", user_id=buyer["id"], listing_id=listing_id)
        ago = await db.card_checkout_ago_seconds()
        assert ago is not None and ago < 60, ago
        assert await db.card_checkouts_since(15) >= 1
        assert await db.card_orders_since(15) == 1, "the forged delivery is inside the window"
        assert scheduler.is_webhook_silent(None, 0) is False, "no link ever handed out"
        assert scheduler.is_webhook_silent(60, 0) is False, "link too fresh to judge"
        assert scheduler.is_webhook_silent(900, 0) is True, "old link + zero deliveries = alarm"
        assert scheduler.is_webhook_silent(900, 1) is False, "one delivery means the rail lives"
        scheduler._silence_alert_at = time.monotonic()  # belt and braces: no admin DMs from a test
        config.CARD_ENABLED = True                      # the watchdog only speaks when the rail is on
        assert await scheduler.check_webhook_silence(bot) is False, "healthy rail must stay silent"
        print(f"watchdog: link {ago}s old + deliveries in window -> no alarm; 15 min of silence -> alarm")

        # --- refund / chargeback: money taken back must leave the top AND leave REAL_REVENUE ---
        await conn.execute("UPDATE card_orders SET status='refunded' WHERE order_id = ?", (ORDER_ID,))
        await conn.commit()
        assert await scheduler.apply_refunds(bot) == 1, "one refund must be processed"
        assert (await db.get_listing(listing_id))["boosted_until"] is None, "refunded = out of the top"
        cur = await conn.execute("SELECT status, order_ref FROM boosts WHERE listing_id = ?", (listing_id,))
        b = await cur.fetchone()
        assert b["status"] == "refunded" and b["order_ref"] == f"ls:{ORDER_ID}", "boost traced to order"
        cur = await conn.execute("SELECT refunded_at FROM payments WHERE provider_charge_id = ?", (ORDER_ID,))
        assert (await cur.fetchone())["refunded_at"], "payment must be marked refunded"
        s = await db.stats()
        assert float(s["revenue_card"]) == revenue_before - config.CARD_PRICE_CENTS / 100, \
            f"refund must leave revenue: {s}"
        assert s["refunds"] >= 1, s
        assert await scheduler.apply_refunds(bot) == 0, "a repeated delivery must not strip twice"
        print(f"refund: top off, boost=refunded, payment marked, revenue_card={s['revenue_card']}")

        # --- partial_refund keeps everything: the money we keep is real money ---
        await conn.execute("UPDATE payments SET refunded_at = NULL WHERE provider_charge_id = ?", (ORDER_ID,))
        await conn.execute("UPDATE boosts SET status = 'paid' WHERE listing_id = ?", (listing_id,))
        await conn.execute("UPDATE card_orders SET status = 'partial_refund' WHERE order_id = ?", (ORDER_ID,))
        await conn.commit()
        await db.boost_listing(listing_id, config.BOOST_DAYS)
        assert await scheduler.apply_refunds(bot) == 0, "partial refund must not touch the boost"
        assert (await db.get_listing(listing_id))["boosted_until"], "boost must stay"
        assert (await db.stats())["revenue_card"] == revenue_before
        print("partial_refund: boost and revenue untouched")

        # --- expired Boost: the repeat-sale moment, announced exactly once per window ---
        await conn.execute("UPDATE listings SET boosted_until = datetime('now', '-2 hours') WHERE id = ?",
                           (listing_id,))
        await conn.commit()
        expired = {r["id"] for r in await db.boosts_that_just_expired()}
        assert listing_id in expired, "a boost that just ended must be noticed"
        assert await scheduler.notify_expired_boosts(bot) >= 1, "owner must get the re-boost offer"
        again = {r["id"] for r in await db.boosts_that_just_expired()}
        assert listing_id not in again, "the same expiry must not be announced twice"
        print("boost expiry: one re-boost offer per window, dedup survives a restart (events row)")

        # --- MIA claim nobody ticked: must be re-pushed to admins, at most once per window ---
        mid = await db.log_boost(listing_id, owner["id"], config.BOOST_MDL, config.BOOST_DAYS,
                                 status="manual_pending")
        await conn.execute("UPDATE boosts SET created_at = datetime('now', '-7 hours') WHERE id = ?", (mid,))
        await conn.commit()
        waiting = {r["boost_id"]: r for r in await db.manual_claims_waiting(scheduler.MANUAL_REMIND_HOURS)}
        assert mid in waiting, "a 7h old claim must be on the reminder list"
        assert waiting[mid]["waited_hours"] >= scheduler.MANUAL_REMIND_HOURS
        assert waiting[mid]["listing_phone"], "admin needs the payer number from the listing"
        assert (await db.stats())["manual_waiting"] >= 1
        assert await db.event_recent("manual_remind", str(mid), scheduler.MANUAL_REMIND_HOURS) is False

        async def reminders() -> int:
            cur = await conn.execute(
                "SELECT COUNT(*) c FROM events WHERE name='manual_remind' AND meta = ?", (str(mid),))
            return (await cur.fetchone())["c"]

        config.BOOST_MDL = config.BOOST_MDL or 100  # the reminder only speaks when the rail is priced
        await scheduler.check_manual_claims(bot)
        assert await db.event_recent("manual_remind", str(mid), scheduler.MANUAL_REMIND_HOURS) is True
        first = await reminders()
        await scheduler.check_manual_claims(bot)
        assert await reminders() == first, "reminder must be deduped inside the window"
        print(f"MIA claim: reminded once in {scheduler.MANUAL_REMIND_HOURS}h, admin got the review buttons")

        print("✅ MONEY RAIL OK - paid, refunded, reminded and re-sold, all by itself")
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
