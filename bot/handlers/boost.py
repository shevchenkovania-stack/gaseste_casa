from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, LabeledPrice, Message, PreCheckoutQuery

import config
import db
import keyboards

router = Router()


async def offer_flow(target: Message, from_user, listing_id: int) -> None:
    """Show boost offer. Works for callback messages and /startapp deep links."""
    row = await db.get_listing(listing_id)
    if not row:
        await target.answer("Объявление не найдено.")
        return
    user = await db.get_or_create_user(from_user.id, from_user.username, from_user.first_name)
    if row["user_id"] != user["id"]:
        await target.answer("Поднять можно только своё объявление.")
        return
    await db.log_event("boost_click", user_id=user["id"], listing_id=listing_id)
    text = (
        f"\U0001F680 <b>Boost объявления #{listing_id}</b>\n\n"
        f"Твоё объявление будет показываться <b>первым</b> в поиске и выделяться \u2B50 "
        f"в течение <b>{config.BOOST_DAYS} дней</b>.\n\n"
        f"Стоимость: <b>{config.BOOST_STARS} Telegram Stars</b> \u2B50\n"
        "Оплата проходит внутри Telegram, безопасно."
    )
    await target.answer(text, parse_mode="HTML",
                        reply_markup=keyboards.boost_kb(listing_id, config.BOOST_STARS, config.BOOST_DAYS))


@router.callback_query(F.data.startswith("boost:"))
async def boost_offer(cb: CallbackQuery) -> None:
    listing_id = int(cb.data.split(":", 1)[1])
    await cb.answer()
    await offer_flow(cb.message, cb.from_user, listing_id)


@router.callback_query(F.data.startswith("boostpay:"))
async def boost_pay(cb: CallbackQuery, bot: Bot) -> None:
    listing_id = int(cb.data.split(":", 1)[1])
    row = await db.get_listing(listing_id)
    await cb.answer()
    if not row:
        return
    user = await db.get_or_create_user(cb.from_user.id, cb.from_user.username, cb.from_user.first_name)
    if row["user_id"] != user["id"]:
        await cb.message.answer("Это не твоё объявление.")
        return
    await db.log_event("boost_payment_attempt", user_id=user["id"], listing_id=listing_id)
    await bot.send_invoice(
        chat_id=cb.message.chat.id,
        title=f"Boost #{listing_id}",
        description=f"Поднятие объявления в топ на {config.BOOST_DAYS} дней",
        payload=f"boost:{listing_id}",
        provider_token="",
        currency=config.STARS_CURRENCY,
        prices=[LabeledPrice(label="Boost", amount=config.BOOST_STARS)],
    )


@router.pre_checkout_query()
async def pre_checkout(q: PreCheckoutQuery) -> None:
    await q.answer(ok=True)


@router.message(F.successful_payment)
async def on_paid(message: Message, bot: Bot) -> None:
    sp = message.successful_payment
    payload = sp.invoice_payload or ""
    user = await db.get_or_create_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    if payload.startswith("boost:"):
        listing_id = int(payload.split(":", 1)[1])
        days = config.BOOST_DAYS
        await db.boost_listing(listing_id, days)
        await db.log_boost(listing_id, user["id"], sp.total_amount, days, status="paid")
        await db.log_payment(
            user_id=user["id"], listing_id=listing_id, purpose="boost",
            stars=sp.total_amount, currency=sp.currency,
            telegram_charge_id=sp.telegram_payment_charge_id,
            provider_charge_id=sp.provider_payment_charge_id,
        )
        await db.log_event("boost_paid", user_id=user["id"], listing_id=listing_id, meta=str(sp.total_amount))
        await message.answer(
            f"\u2705 Оплата получена! Объявление <b>#{listing_id}</b> поднято на <b>{days} дней</b> \U0001F680",
            parse_mode="HTML",
            reply_markup=keyboards.main_menu(),
        )
        for admin in config.ADMIN_IDS:
            try:
                await bot.send_message(admin, f"\U0001F4B0 <b>Новый платёж</b>\nBoost #{listing_id}: {sp.total_amount} Stars")
            except Exception:
                pass
    else:
        await message.answer("\u2705 Платёж получен. Спасибо!", reply_markup=keyboards.main_menu())
