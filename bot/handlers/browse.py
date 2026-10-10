from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import db
import keyboards
import render
from constants import DEAL_LABELS, DISTRICTS, PTYPE_LABELS

router = Router()
PAGE = 10


class Search(StatesGroup):
    deal = State()
    ptype = State()
    district = State()
    results = State()


def _deal_kb() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=v, callback_data=f"fdeal:{k}")] for k, v in DEAL_LABELS.items()]
    rows.append([InlineKeyboardButton(text="\U0001F440 Показать всё", callback_data="fdeal:all")])
    rows.append([InlineKeyboardButton(text="\u2b05\uFE0F Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _ptype_kb() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=v, callback_data=f"fptype:{k}")] for k, v in PTYPE_LABELS.items()]
    rows.append([InlineKeyboardButton(text="Любой тип", callback_data="fptype:all")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _district_kb() -> InlineKeyboardMarkup:
    rows = []
    pair = []
    for d in DISTRICTS:
        pair.append(InlineKeyboardButton(text=d, callback_data=f"fdist:{d}"))
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)
    rows.append([InlineKeyboardButton(text="\U0001F30D Любой район", callback_data="fdist:all")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "menu:search")
async def start_search(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(Search.deal)
    await cb.answer()
    await cb.message.answer("\U0001F50D Что ищем?", reply_markup=_deal_kb())


@router.callback_query(Search.deal, F.data.startswith("fdeal:"))
async def f_deal(cb: CallbackQuery, state: FSMContext) -> None:
    v = cb.data.split(":", 1)[1]
    await state.update_data(deal=None if v == "all" else v)
    await state.set_state(Search.ptype)
    await cb.answer()
    await cb.message.answer("Тип объекта?", reply_markup=_ptype_kb())


@router.callback_query(Search.ptype, F.data.startswith("fptype:"))
async def f_ptype(cb: CallbackQuery, state: FSMContext) -> None:
    v = cb.data.split(":", 1)[1]
    await state.update_data(ptype=None if v == "all" else v)
    await state.set_state(Search.district)
    await cb.answer()
    await cb.message.answer("Район?", reply_markup=_district_kb())


@router.callback_query(Search.district, F.data.startswith("fdist:"))
async def f_dist(cb: CallbackQuery, state: FSMContext) -> None:
    v = cb.data.split(":", 1)[1]
    await state.update_data(district=None if v == "all" else v, page=0)
    await state.set_state(Search.results)
    await cb.answer()
    await show_results(cb.message, state)


@router.callback_query(F.data == "back:search")
async def back_search(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    data = await state.get_data()
    if not data:
        await state.set_state(Search.deal)
        await cb.message.answer("\U0001F50D Что ищем?", reply_markup=_deal_kb())
        return
    await state.set_state(Search.results)
    await show_results(cb.message, state)


async def show_results(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    page = data.get("page", 0)
    deal, ptype, district = data.get("deal"), data.get("ptype"), data.get("district")
    total = await db.count_search_listings(deal=deal, ptype=ptype, district=district)
    rows = await db.search_listings(
        deal=deal, ptype=ptype, district=district, limit=PAGE, offset=page * PAGE
    )
    if total == 0:
        await message.answer(
            "Ничего не найдено. Попробуй другие фильтры.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="\U0001F50D Изменить фильтры", callback_data="menu:search")],
                [InlineKeyboardButton(text="\U0001F3E0 Меню", callback_data="menu:home")],
            ]),
        )
        return
    kb_rows = []
    for r in rows:
        kb_rows.append([InlineKeyboardButton(text=render.listing_button_text(r), callback_data=f"view:{r['id']}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="\u2b05\uFE0F", callback_data="page:prev"))
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{(total - 1) // PAGE + 1}", callback_data="noop"))
    if (page + 1) * PAGE < total:
        nav.append(InlineKeyboardButton(text="\u27A1\uFE0F", callback_data="page:next"))
    if nav:
        kb_rows.append(nav)
    kb_rows.append([InlineKeyboardButton(text="\U0001F50D Фильтры", callback_data="menu:search")])
    await message.answer(
        f"Найдено: <b>{total}</b>. Выбери объявление:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows),
    )


@router.callback_query(Search.results, F.data.in_({"page:next", "page:prev"}))
async def paginate(cb: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    page = data.get("page", 0)
    page = page + 1 if cb.data == "page:next" else max(0, page - 1)
    await state.update_data(page=page)
    await cb.answer()
    await show_results(cb.message, state)


@router.callback_query(F.data == "noop")
async def noop(cb: CallbackQuery) -> None:
    await cb.answer()


@router.callback_query(F.data.startswith("view:"))
async def view_listing(cb: CallbackQuery) -> None:
    listing_id = int(cb.data.split(":", 1)[1])
    row = await db.get_listing(listing_id)
    await cb.answer()
    if not row:
        await cb.message.answer("Объявление не найдено.")
        return
    user = await db.get_or_create_user(cb.from_user.id, cb.from_user.username, cb.from_user.first_name)
    is_owner = row["user_id"] == user["id"]
    if not is_owner and row["status"] != "active":
        await cb.message.answer("Объявление недоступно.")
        return
    if not is_owner:
        await db.inc_views(listing_id)
        await db.log_event("listing_view", user_id=user["id"], listing_id=listing_id)
    await render.send_listing(cb.bot, cb.message.chat.id, row, owner=is_owner)


@router.callback_query(F.data.startswith("contact:"))
async def contact(cb: CallbackQuery) -> None:
    listing_id = int(cb.data.split(":", 1)[1])
    row = await db.get_listing(listing_id)
    await cb.answer()
    if not row:
        return
    phone = row["phone"]
    if phone:
        await cb.message.answer(
            f"\U0001F4DE Контакт: <code>{render.esc(phone)}</code>\n"
            "Нажми на номер, чтобы скопировать.",
            parse_mode="HTML",
        )
    else:
        username = None
        cur = await db.get_user_by_id(row["user_id"])
        if cur:
            username = cur["username"]
        if username:
            await cb.message.answer(f"Контакт: https://t.me/{username}")
        else:
            await cb.message.answer("Контакт не указан.")
    await db.log_event("contact_click", user_id=None, listing_id=listing_id)
