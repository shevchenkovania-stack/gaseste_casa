from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

import config
import db
import keyboards

router = Router()


def is_admin(tg_id: int) -> bool:
    return tg_id in config.ADMIN_IDS


@router.callback_query(F.data.startswith("mod:"))
async def moderate(cb: CallbackQuery, bot: Bot) -> None:
    if not is_admin(cb.from_user.id):
        await cb.answer("Нет доступа", show_alert=True)
        return
    _, action, sid = cb.data.split(":")
    listing_id = int(sid)
    row = await db.get_listing(listing_id)
    await cb.answer()
    if not row:
        await cb.message.answer("Объявление не найдено.")
        return
    status = "active" if action == "approve" else "rejected"
    await db.set_listing_status(listing_id, status)
    await db.log_event(f"moderation_{action}", listing_id=listing_id)
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.message.answer(f"Объявление #{listing_id}: <b>{status}</b>", parse_mode="HTML")
    owner = await db.get_user_by_id(row["user_id"])
    if owner:
        if status == "active":
            note = f"\u2705 Твоё объявление <b>#{listing_id}</b> одобрено и опубликовано!"
        else:
            note = f"\u274C Твоё объявление <b>#{listing_id}</b> отклонено модератором."
        try:
            await bot.send_message(owner["tg_id"], note, parse_mode="HTML", reply_markup=keyboards.main_menu())
        except Exception:
            pass


@router.message(Command("stats"))
async def stats(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    s = await db.stats()
    text = (
        "<b>Статистика</b>\n"
        f"Пользователи: {s['users']}\n"
        f"Объявлений: {s['listings']} (активных {s['active']}, на модерации {s['pending']})\n"
        f"Boost'ов: {s['boosts']}\n"
        f"Платежей: {s['payments']}\n"
        f"REAL_REVENUE (Stars \u2B50): <b>{s['revenue_stars']}</b>"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("admin"))
async def admin_help(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        "Админ-команды:\n/stats — статистика\n/pending — объявления на модерации",
    )


@router.message(Command("pending"))
async def pending(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    rows = await db.search_listings(limit=20)
    # show pending separately
    import aiosqlite
    cur = await db._db().execute("SELECT * FROM listings WHERE status='pending' ORDER BY created_at LIMIT 20")
    pend = await cur.fetchall()
    if not pend:
        await message.answer("Нет объявлений на модерации.")
        return
    for r in pend:
        await message.answer(
            f"#{r['id']} {r['deal']} · {r['ptype']} · {r['district']} · {r['price']}{r['currency']}",
            reply_markup=keyboards.moderation_kb(r["id"]),
        )
