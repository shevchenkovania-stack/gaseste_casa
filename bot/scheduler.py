"""Periodic jobs. Two matter for revenue: the Boost nudge and the card payment inbox.

The inbox job is what makes card money real: Lemon Squeezy posts the order to the Mini App
process, that process only stores it, and here (single writer) it becomes a boost + payment row.
Deterministic by design - plain SQL, plain arithmetic, no LLM, no heuristics.
"""
import asyncio
import logging

from aiogram import Bot

import config
import db
import keyboards

log = logging.getLogger("chiriebot.scheduler")
CARD_TICK_SECONDS = 60  # how often the card payment inbox is checked


async def nudge_unboosted(bot: Bot) -> int:
    """Offer a Boost to owners of live, currently unboosted listings."""
    rows = await db.listings_to_nudge(config.NUDGE_AFTER_DAYS, config.NUDGE_COOLDOWN_DAYS)
    sent = 0
    for row in rows:
        owner = await db.get_user_by_id(row["user_id"])
        if not owner:
            await db.mark_nudged(row["id"])
            continue
        rooms = f"{row['rooms']}-комн. " if row["rooms"] else ""
        text = (
            f"\u23F3 Твоё объявление <b>#{row['id']}</b> "
            f"({rooms}{row['district'] or '—'} \u00B7 {row['price']} {row['currency']}) "
            "в базе, но сейчас не в топе.\n"
            f"Просмотров: <b>{row['views']}</b>\n\n"
            + keyboards.boost_pitch()
        )
        try:
            await bot.send_message(
                owner["tg_id"], text, parse_mode="HTML",
                reply_markup=keyboards.boost_kb(row["id"]),
            )
        except Exception as e:  # blocked / deleted chat: don't retry forever
            log.info("nudge skipped #%s (user %s): %s", row["id"], owner["tg_id"], e)
        await db.mark_nudged(row["id"])
        await db.log_event("boost_nudge", user_id=owner["id"], listing_id=row["id"])
        sent += 1
    return sent


async def apply_card_orders(bot: Bot) -> int:
    """Credit Boost for card orders the provider reported as paid.

    The webhook only stores rows; this is the single place where card money becomes a boost.
    Idempotent by the applied flag, so a restart or a repeated delivery can never pay twice.
    """
    applied = 0
    for row in await db.card_orders_to_apply():
        listing = await db.get_listing(row["listing_id"])
        buyer = await db.get_user_by_tg_id(row["tg_id"]) if row["tg_id"] else None
        if not listing or not buyer:
            log.warning("card order %s: no listing #%s or user %s, left unapplied",
                        row["order_id"], row["listing_id"], row["tg_id"])
            await db.log_event("card_order_unmatched", listing_id=row["listing_id"],
                               meta=row["order_id"])
            continue
        is_test = bool(row["test_mode"])
        amount = row["amount_cents"] / 100
        await db.boost_listing(row["listing_id"], config.BOOST_DAYS)
        await db.log_boost(row["listing_id"], buyer["id"], 0, config.BOOST_DAYS, status="paid")
        await db.log_payment(user_id=buyer["id"], listing_id=row["listing_id"],
                             purpose="boost_card_test" if is_test else "boost_card",
                             stars=0, currency=row["currency"], telegram_charge_id=None,
                             provider_charge_id=row["order_id"], amount=amount, is_test=is_test)
        await db.mark_card_order_applied(row["id"])
        await db.log_event("boost_card_paid", user_id=buyer["id"], listing_id=row["listing_id"],
                           meta=f"{row['order_id']} {amount} {row['currency']}")
        tag = "\U0001F9EA Тестовый платёж принят. " if is_test else "\u2705 Оплата картой получена! "
        try:
            await bot.send_message(
                buyer["tg_id"],
                f"{tag}Объявление <b>#{row['listing_id']}</b> поднято в топ на "
                f"<b>{config.BOOST_DAYS} дней</b> \U0001F680",
                parse_mode="HTML", reply_markup=keyboards.main_menu(),
            )
        except Exception as e:
            log.info("card notice skipped for %s: %s", buyer["tg_id"], e)
        for admin in config.ADMIN_IDS:
            try:
                await bot.send_message(
                    admin,
                    f"\U0001F4B3 <b>Новый платёж</b>\nBoost #{row['listing_id']}: "
                    f"{amount:.2f} {row['currency']} картой (Lemon Squeezy)"
                    + ("\n⚠️ тестовый режим — денег по этому заказу нет" if is_test else ""),
                )
            except Exception:
                pass
        applied += 1
    return applied


async def run(bot: Bot) -> None:
    """Sleep first, then work forever. Exceptions never kill the loop."""
    elapsed = 0
    while True:
        await asyncio.sleep(CARD_TICK_SECONDS)
        elapsed += CARD_TICK_SECONDS
        try:
            n = await apply_card_orders(bot)
            if n:
                log.info("card boosts applied: %s", n)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("card apply pass failed")
        if elapsed >= config.NUDGE_INTERVAL_HOURS * 3600:
            elapsed = 0
            try:
                n = await nudge_unboosted(bot)
                if n:
                    log.info("boost nudges sent: %s", n)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("nudge pass failed")
