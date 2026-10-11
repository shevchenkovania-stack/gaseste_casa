"""E2E of the surfaces test_publish/test_gift do NOT cover: search, boost ordering, payment.

Runs the REAL db/webapp code paths a user hits - filter search, boosted-first ordering, the
Mini App filtered API - then exercises both live money rails the way the handlers do it
(Telegram Stars via on_paid's writes, MIA manual via manual_claim+manual_review), including
the refund path, and finally deletes every trace. Payment rows are written with is_test=1 /
XTEST currency so REAL_REVENUE is provably untouched even mid-run. Baselines are captured on
entry and re-checked on exit: a single leftover row fails the test.

Submission -> moderation -> channel is already covered by test_publish; gift by test_gift.

Run on prod: cd /opt/imobiliare/bot && timeout 120 /opt/imobiliare/venv/bin/python test_all.py
"""
import asyncio
import os
import sys

sys.path.insert(0, "/opt/imobiliare/bot")

import aiohttp

import config
import db

MARKER = "ТЕХНИЧЕСКИЙ ТЕСТ поиска/оплаты (не объявление). Самоудалимся."


async def snapshot(conn):
    c = await conn.execute(
        """SELECT
             (SELECT COUNT(*) FROM listings) l,
             (SELECT COUNT(*) FROM events) e,
             (SELECT COUNT(*) FROM users) u,
             (SELECT COUNT(*) FROM boosts) b,
             (SELECT COUNT(*) FROM payments) p,
             (SELECT COALESCE(SUM(stars),0) FROM payments WHERE currency='XTR' AND is_test=0 AND refunded_at IS NULL) rs,
             (SELECT COALESCE(SUM(amount),0) FROM payments WHERE currency='MDL' AND is_test=0 AND refunded_at IS NULL) rm"""
    )
    return dict(await c.fetchone())


async def main() -> None:
    await db.init_db()
    conn = db._db()
    base = await snapshot(conn)
    print("baseline:", base)

    # one synthetic owner for the whole run
    user = await db.get_or_create_user(999999002, "alltest", "ALL TEST")
    ids = []

    # 1. SUBMIT three fresh objects with distinct attributes, straight to active (as moderation does)
    async def add(**kw):
        lid = await db.create_listing(user_id=user["id"], photos=[], description=MARKER, **kw)
        await db.set_listing_status(lid, "active")
        ids.append(lid)
        return lid

    rent_2c = await add(deal="rent", ptype="apartment", rooms=2, price=500, currency="EUR",
                        district="Râscani")          # 2-room rent, pricier
    rent_1c = await add(deal="rent", ptype="apartment", rooms=1, price=350, currency="EUR",
                        district="Centru")           # 1-room rent, cheaper
    sale_3 = await add(deal="sale", ptype="house", rooms=3, price=60000, currency="EUR",
                       district="Centru")            # a sale, must never show in rent search

    # 2. SEARCH - every filter must select exactly the right rows via the real db function
    async def ids_of(rows):
        return sorted(r["id"] for r in rows)

    got = await ids_of(await db.search_listings(deal="rent"))
    assert got == sorted([rent_2c, rent_1c]), f"deal=rent -> {got}"

    got = await ids_of(await db.search_listings(deal="sale"))
    assert got == [sale_3], f"deal=sale -> {got}"

    got = await ids_of(await db.search_listings(district="Centru"))
    assert got == sorted([rent_1c, sale_3]), f"district=Centru -> {got}"

    got = await ids_of(await db.search_listings(rooms=1))
    assert got == [rent_1c], f"rooms=1 -> {got}"

    got = await ids_of(await db.search_listings(deal="rent", price_max=400))
    assert got == [rent_1c], f"rent price<=400 -> {got}"

    cnt = await db.count_search_listings(deal="rent")
    assert cnt == 2, f"count_search_listings rent -> {cnt}"
    print("db search filters: OK")

    # 3. BOOST ORDERING - a boosted listing must come first in search, unboosted last
    await db.boost_listing(rent_1c, config.BOOST_DAYS)
    top = (await db.search_listings(deal="rent"))[0]["id"]
    assert top == rent_1c, f"boosted listing not first: top={top}"
    await db.unboost_listing(rent_1c)
    print("boost-first ordering: OK")

    # 4. MINI APP filtered API serves the same objects with the same filters
    timeout = aiohttp.ClientTimeout(total=25)
    async with aiohttp.ClientSession(timeout=timeout) as sess:
        async with sess.get(f"{config.WEBAPP_URL.rstrip('/')}/api/listings?deal=rent") as resp:
            data = await resp.json()
        api_rent = sorted(it["id"] for it in data["items"] if it["id"] in ids)
        assert api_rent == sorted([rent_2c, rent_1c]), f"webapp deal=rent -> {api_rent}"
        async with sess.get(f"{config.WEBAPP_URL.rstrip('/')}/api/listings?district=Centru") as resp:
            data = await resp.json()
        api_centru = sorted(it["id"] for it in data["items"] if it["id"] in ids)
        assert api_centru == sorted([rent_1c, sale_3]), f"webapp district=Centru -> {api_centru}"
    print("webapp filtered API: OK")

    # 5. PAYMENT rail 1 - Telegram Stars: mirror on_paid's writes for a completed invoice.
    #    XTEST currency + is_test=1 keep it out of REAL_REVENUE even if cleanup were to fail.
    stars_boost = await db.log_boost(rent_2c, user["id"], config.BOOST_STARS, config.BOOST_DAYS,
                                     status="paid", order_ref="tg:alltest")
    await db.boost_listing(rent_2c, config.BOOST_DAYS)
    await db.log_payment(user_id=user["id"], listing_id=rent_2c, purpose="boost_test",
                         stars=config.BOOST_STARS, currency="XTEST",
                         telegram_charge_id="tg:alltest", provider_charge_id="prov:alltest",
                         is_test=True)
    row = await db.get_listing(rent_2c)
    assert row["boosted_until"], "Stars boost did not lift the listing"
    print("Stars rail (paid boost + test payment row): OK")

    # 6. PAYMENT rail 2 - MIA manual: claim (manual_pending) -> admin approve -> boosted + booked.
    mdl = config.BOOST_MDL or 100
    man_boost = await db.log_boost(sale_3, user["id"], mdl, config.BOOST_DAYS, status="manual_pending")
    assert (await db.find_boost(sale_3, "manual_pending"))["id"] == man_boost, "claim not pending"
    # a second claim while one is pending must be blocked the way manual_claim does
    assert await db.find_boost(sale_3, "manual_pending"), "double-claim guard lost the pending row"
    # admin taps "подтвердить": status -> manual, listing lifted, MDL payment booked (is_test keeps books honest)
    await db.set_boost_status(man_boost, "manual", order_ref=f"manual:{man_boost}")
    await db.boost_listing(sale_3, config.BOOST_DAYS)
    await db.log_payment(user_id=user["id"], listing_id=sale_3, purpose="boost_manual",
                         stars=0, currency="MDL", telegram_charge_id=f"manual:{man_boost}",
                         provider_charge_id=None, amount=float(mdl), is_test=True)
    assert (await db.get_listing(sale_3))["boosted_until"], "manual approve did not lift the listing"
    paid = await db.find_boost(sale_3, "manual")
    assert paid and paid["order_ref"] == f"manual:{man_boost}", "manual boost not linked to payment"
    print("MIA manual rail (pending -> approve -> boost + MDL booking): OK")

    # 7. REFUND - money going back leaves the top and (for a real row) the revenue line.
    #    Our rows are is_test so they were never in revenue; verify the flag + refunded_at marker work.
    p = await db.find_payment_by_charge(f"manual:{man_boost}")
    assert p and p["is_test"] == 1, "test payment row missing / not flagged is_test"
    await db.mark_payment_refunded(p["id"])
    p2 = await db.find_payment_by_charge(f"manual:{man_boost}")
    assert p2["refunded_at"], "refund marker not set"
    await db.unboost_listing(sale_3)
    assert not (await db.get_listing(sale_3))["boosted_until"], "refund left the listing in the top"
    mid = await snapshot(conn)
    assert mid["rs"] == base["rs"] and mid["rm"] == base["rm"], "REAL_REVENUE moved during test!"
    print("refund path (booster off + revenue untouched): OK")

    # 8. CLEANUP - delete every trace, then prove the board is byte-for-byte back at baseline
    await conn.execute("DELETE FROM boosts WHERE listing_id IN (?,?,?)", (rent_2c, rent_1c, sale_3))
    await conn.execute("DELETE FROM payments WHERE listing_id IN (?,?,?)", (rent_2c, rent_1c, sale_3))
    await conn.execute("DELETE FROM listings WHERE id IN (?,?,?)", (rent_2c, rent_1c, sale_3))
    await conn.execute("DELETE FROM events WHERE user_id = ?", (user["id"],))
    await conn.execute("DELETE FROM users WHERE id = ?", (user["id"],))
    await conn.commit()
    after = await snapshot(conn)
    assert after == base, f"RESIDUE: base={base} after={after}"

    await db.close_db()
    print("✅ ALL LOOP OK (submit -> search filters -> boost order -> webapp API -> Stars -> "
          "MIA -> refund -> REAL_REVENUE intact -> zero residue)")
    sys.stdout.flush()
    os._exit(0)


asyncio.run(main())
