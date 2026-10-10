import asyncio

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, LabeledPrice, Message

import config
import db
import keyboards
import publish
import scheduler

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
            note = (f"\u2705 Твоё объявление <b>#{listing_id}</b> одобрено и опубликовано!\n"
                    "Его уже видят в поиске и в канале. Хочешь быть первым? Жми Boost \U0001F680")
            try:
                await publish.publish_listing(bot, row)
            except Exception:
                pass  # publishing to channel/webapp must never block moderation
        else:
            note = f"\u274C Твоё объявление <b>#{listing_id}</b> отклонено модератором."
        try:
            await bot.send_message(owner["tg_id"], note, parse_mode="HTML", reply_markup=keyboards.main_menu())
        except Exception:
            pass


@router.callback_query(F.data.startswith("manapp:") | F.data.startswith("manrej:"))
async def manual_review(cb: CallbackQuery, bot: Bot) -> None:
    """Admin confirms a manual MDL transfer (manapp) or rejects it (manrej)."""
    if not is_admin(cb.from_user.id):
        await cb.answer("Нет доступа", show_alert=True)
        return
    action, sid = cb.data.split(":", 1)
    boost_id = int(sid)
    boost = await db.get_boost(boost_id)
    await cb.answer()
    if not boost:
        await cb.message.answer("Заявка не найдена (возможно, уже обработана).")
        return
    if boost["status"] != "manual_pending":
        await cb.message.answer(f"Заявка уже в статусе «{boost['status']}».")
        return
    listing_id = boost["listing_id"]
    owner = await db.get_user_by_id(boost["user_id"])
    await cb.message.edit_reply_markup(reply_markup=None)

    if action == "manapp":
        await db.set_boost_status(boost_id, "manual")
        await db.boost_listing(listing_id, boost["days"])
        # boosts.stars holds the agreed MDL price for manual claims (set at claim time)
        amount_mdl = float(boost["stars"] or config.BOOST_MDL)
        await db.log_payment(user_id=boost["user_id"], listing_id=listing_id, purpose="boost_manual",
                             stars=0, currency="MDL", telegram_charge_id=f"manual:{boost_id}",
                             provider_charge_id=None, amount=amount_mdl)
        await db.log_event("boost_manual_paid", user_id=boost["user_id"], listing_id=listing_id,
                           meta=str(int(amount_mdl)))
        await cb.message.answer(f"✅ Boost #{listing_id} активирован на {boost['days']} дней. "
                                f"Сумма: {int(amount_mdl)} MDL.")
        if owner:
            try:
                await bot.send_message(
                    owner["tg_id"],
                    f"\U0001F4B0 Платёж получен, спасибо!\nОбъявление <b>#{listing_id}</b> "
                    f"поднято в топ на <b>{boost['days']} дней</b> \U0001F680",
                    parse_mode="HTML", reply_markup=keyboards.main_menu(),
                )
            except Exception:
                pass
    else:
        await db.set_boost_status(boost_id, "manual_rejected")
        await cb.message.answer(f"❌ Платёж по заявке #{boost_id} отклонён.")
        if owner:
            try:
                await bot.send_message(
                    owner["tg_id"],
                    "⚠️ Деньги не нашли на счёте. Проверь реквизиты и комментарий к переводу "
                    f"и нажми «Я перевёл» ещё раз по объявлению #{listing_id}.",
                    reply_markup=keyboards.main_menu(),
                )
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
        f"Платежей: {s['payments']} (тестовых: {s['test_payments']})\n"
        f"REAL_REVENUE Stars \u2B50: <b>{s['revenue_stars']}</b>\n"
        f"REAL_REVENUE MDL \U0001F4B0: <b>{s['revenue_mdl']}</b>"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("admin"))
async def admin_help(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        "Админ-команды:\n"
        "/stats — статистика\n"
        "/pending — объявления на модерации\n"
        "/nudge — сразу предложить Boost тем, кто не в топе\n"
        "/broadcast <текст> — рассылка всем пользователям бота",
    )


@router.message(Command("nudge"))
async def nudge_now(message: Message, bot: Bot) -> None:
    """Force a nudge pass without waiting for the scheduler."""
    if not is_admin(message.from_user.id):
        return
    n = await scheduler.nudge_unboosted(bot)
    await message.answer(f"Предложений Boost отправлено: {n}")


@router.message(Command("broadcast"))
async def broadcast(message: Message, bot: Bot) -> None:
    if not is_admin(message.from_user.id):
        return
    text = (message.text or "").partition("\n")[2].strip()
    if not text:
        await message.answer("Использование: /broadcast <текст>")
        return
    ids = [tg for tg in await db.all_user_tg_ids() if tg not in config.ADMIN_IDS]
    ok = 0
    for tg in ids:
        try:
            await bot.send_message(tg, text, parse_mode="HTML", reply_markup=keyboards.main_menu())
            ok += 1
        except Exception:
            pass  # blocked the bot
        await asyncio.sleep(0.05)
    await db.log_event("broadcast", user_id=message.from_user.id, meta=f"{ok}/{len(ids)}")
    await message.answer(f"Рассылка готова: доставлено {ok} из {len(ids)}.")


@router.message(Command("pending"))
async def pending(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
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
