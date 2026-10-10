"""Periodic jobs. Only one matters for revenue: the Boost nudge.

Deterministic by design - plain SQL selection + a message with the same
payment keyboard the owner gets in the bot. No LLM, no heuristics.
"""
import asyncio
import logging

from aiogram import Bot

import config
import db
import keyboards

log = logging.getLogger("chiriebot.scheduler")


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
            f"\U0001F680 <b>Boost</b> \u2014 {config.BOOST_STARS} Stars \u2B50: объявление поднимается "
            f"на первое место в поиске на <b>{config.BOOST_DAYS} дней</b>."
        )
        try:
            await bot.send_message(
                owner["tg_id"], text, parse_mode="HTML",
                reply_markup=keyboards.boost_kb(row["id"], config.BOOST_STARS, config.BOOST_DAYS),
            )
        except Exception as e:  # blocked / deleted chat: don't retry forever
            log.info("nudge skipped #%s (user %s): %s", row["id"], owner["tg_id"], e)
        await db.mark_nudged(row["id"])
        await db.log_event("boost_nudge", user_id=owner["id"], listing_id=row["id"])
        sent += 1
    return sent


async def run(bot: Bot) -> None:
    """Sleep first, then run the job forever. Exceptions never kill the loop."""
    delay = config.NUDGE_INTERVAL_HOURS * 3600
    while True:
        await asyncio.sleep(delay)
        try:
            n = await nudge_unboosted(bot)
            if n:
                log.info("boost nudges sent: %s", n)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("nudge pass failed")
