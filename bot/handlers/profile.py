from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

import db
import keyboards
import render
from constants import DEAL_LABELS, PTYPE_LABELS, STATUS_LABELS

router = Router()


@router.callback_query(F.data == "menu:my")
async def my_listings(cb: CallbackQuery) -> None:
    await cb.answer()
    user = await db.get_or_create_user(cb.from_user.id, cb.from_user.username, cb.from_user.first_name)
    rows = await db.get_user_listings(user["id"])
    if not rows:
        await cb.message.answer(
            "У тебя пока нет объявлений.\nРазместить можно бесплатно \U0001F447",
            reply_markup=keyboards.main_menu(),
        )
        return
    kb_rows = []
    for r in rows:
        label = f"#{r['id']} {DEAL_LABELS.get(r['deal'], r['deal'])} · {PTYPE_LABELS.get(r['ptype'], r['ptype'])} · {r['price']}{r['currency']} · {STATUS_LABELS.get(r['status'], r['status'])}"
        kb_rows.append([InlineKeyboardButton(text=label[:60], callback_data=f"view:{r['id']}")])
    kb_rows.append([InlineKeyboardButton(text="\U0001F3E0 Меню", callback_data="menu:home")])
    await cb.message.answer(
        "Твои объявления:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows),
    )
