import html
import re

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import config
import db
import keyboards
from constants import DEAL_LABELS, DISTRICTS, PTYPE_LABELS, ROOMS

router = Router()

# Linear spine of the wizard - "Назад" walks it one step back, keeping everything already
# answered. The optional detail screens (area/floor/description/phone) share ONE step in
# the numbering, so the wizard honestly says 5 instead of counting every screen.
STEP_ORDER = ("specs", "district", "price", "area", "floor", "description", "phone", "photos", "confirm")

STEP_LABEL = {
    "specs": "Шаг 1/5 · Характеристики",
    "district": "Шаг 2/5 · Район",
    "price": "Шаг 3/5 · Цена",
    "area": "Шаг 4/5 · Детали (необязательно)",
    "floor": "Шаг 4/5 · Детали (необязательно)",
    "description": "Шаг 4/5 · Детали (необязательно)",
    "phone": "Шаг 4/5 · Детали (необязательно)",
    "photos": "Шаг 5/5 · Фото",
    "confirm": "Проверь и опубликуй",
}

# "Пропустить" on an optional step always means "one step forward"
SKIP_NEXT = {"area": "floor", "floor": "description", "description": "phone", "phone": "photos"}


class AddListing(StatesGroup):
    specs = State()
    district = State()
    price = State()
    area = State()
    floor = State()
    description = State()
    phone = State()
    photos = State()
    confirm = State()


def _chip(label: str, active: bool, cb: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=(label + " ✓") if active else label, callback_data=cb)


def _num(txt: str) -> str:
    """Оставить только цифры и разделители: '450 eur', '450€', '450 €' -> '450'.
    Люди вписывают валюту и символы в поле цены - не надо гонять их с начала."""
    return re.sub(r"[^\d.,]", "", txt or "")


def _cancel_btn() -> InlineKeyboardButton:
    return InlineKeyboardButton(text="✖️ Отмена", callback_data="cancel")


def _back_btn() -> InlineKeyboardButton:
    return InlineKeyboardButton(text="⬅️ Назад", callback_data="add:back")


def _skip_kb() -> InlineKeyboardMarkup:
    """Optional step: skip, step back, or cancel - all three always visible."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пропустить ⏭", callback_data="skip:next")],
        [_back_btn()],
        [_cancel_btn()],
    ])


def _back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_back_btn()], [_cancel_btn()]])


def _p_specs(data: dict) -> tuple[str, InlineKeyboardMarkup]:
    text = (
        f"<b>{STEP_LABEL['specs']}</b>\n\n"
        "Сделка, тип объекта и комнаты — три тапа, затем «Далее»."
    )
    rooms_row = [
        _chip(str(r) + ("+" if r == ROOMS[-1] else ""), data.get("rooms") == r, f"rooms:{r}")
        for r in ROOMS
    ]
    rows = [
        [
            _chip("🏠 Аренда", data.get("deal") == "rent", "deal:rent"),
            _chip("💰 Продажа", data.get("deal") == "sale", "deal:sale"),
        ],
        [
            _chip("Квартира", data.get("ptype") == "apartment", "ptype:apartment"),
            _chip("Дом", data.get("ptype") == "house", "ptype:house"),
            _chip("Комната", data.get("ptype") == "room", "ptype:room"),
        ],
        rooms_row,
        [InlineKeyboardButton(text="Далее ➡️", callback_data="add:next")],
        [_cancel_btn()],
    ]
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


def _p_district(data: dict) -> tuple[str, InlineKeyboardMarkup]:
    text = f"<b>{STEP_LABEL['district']}</b>"
    rows: list[list[InlineKeyboardButton]] = []
    pair: list[InlineKeyboardButton] = []
    for d in DISTRICTS:
        pair.append(_chip(d, data.get("district") == d, f"district:{d}"))
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)
    rows.append([_back_btn(), _cancel_btn()])
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


def _p_price(data: dict) -> tuple[str, InlineKeyboardMarkup]:
    hint = f"\nСейчас: <b>{data['price']}</b> — введи новое." if data.get("price") else ""
    text = (
        f"<b>{STEP_LABEL['price']}</b>\n"
        f"Цена в EUR, числом — например <code>450</code>{hint}"
    )
    return text, _back_kb()


def _p_area(data: dict) -> tuple[str, InlineKeyboardMarkup]:
    hint = f" (сейчас {data['area']})" if data.get("area") else ""
    return f"<b>{STEP_LABEL['area']}</b>\n\nПлощадь, м²{hint}:", _skip_kb()


def _p_floor(data: dict) -> tuple[str, InlineKeyboardMarkup]:
    hint = f" (сейчас {data['floor']})" if data.get("floor") else ""
    return (f"<b>{STEP_LABEL['floor']}</b>\n\n"
            f"Этаж, например <code>4</code> или <code>4/9</code>{hint}:"), _skip_kb()


def _p_description(data: dict) -> tuple[str, InlineKeyboardMarkup]:
    hint = ""
    if data.get("description"):
        hint = ("\nСейчас:\n<i>" + html.escape(str(data["description"]))[:200] +
                "</i>\n\nНовый текст заменит старый.")
    return f"<b>{STEP_LABEL['description']}</b>\n\nОписание, до 600 символов:{hint}", _skip_kb()


def _p_phone(data: dict) -> tuple[str, InlineKeyboardMarkup]:
    hint = f"\nСейчас: <code>{html.escape(str(data['phone']))}</code> — введи новый." \
        if data.get("phone") else ""
    return f"<b>{STEP_LABEL['phone']}</b>\n\nКонтактный телефон{hint}:", _skip_kb()


def _p_photos(data: dict) -> tuple[str, InlineKeyboardMarkup]:
    n = len(data.get("photos") or [])
    got = f"\nДобавлено фото: <b>{n}</b> — можешь добавить ещё." if n else ""
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Готово", callback_data="add:photos_done")],
        [InlineKeyboardButton(text="Пропустить ⏭", callback_data="add:photos_skip")],
        [_back_btn()],
        [_cancel_btn()],
    ])
    text = (f"<b>{STEP_LABEL['photos']}</b>\n\n"
            f"Отправь 1–10 фото (каждое — как фото, не файл), затем «Готово»:{got}")
    return text, kb


def _p_confirm(data: dict) -> tuple[str, InlineKeyboardMarkup]:
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Опубликовать", callback_data="add:confirm")],
        [_back_btn()],
        [_cancel_btn()],
    ])
    return _summary(data), kb


PROMPTS = {
    "specs": _p_specs, "district": _p_district, "price": _p_price, "area": _p_area,
    "floor": _p_floor, "description": _p_description, "phone": _p_phone,
    "photos": _p_photos, "confirm": _p_confirm,
}


async def _goto(target: Message, state: FSMContext, step: str) -> None:
    """Move to `step` and turn the message the user is looking at into that step's prompt.
    Button-driven transitions edit in place, so the wizard costs one message per typed
    answer instead of one per screen."""
    await state.set_state(getattr(AddListing, step))
    text, kb = PROMPTS[step](await state.get_data())
    try:
        await target.edit_text(text, parse_mode="HTML", reply_markup=kb)
        return
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            return
    except Exception:
        pass
    await target.answer(text, parse_mode="HTML", reply_markup=kb)


async def begin(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.update_data(photos=[])
    await _goto(message, state, "specs")


# --- step 1: specs (deal + type + rooms on one screen) ----------------------

@router.callback_query(AddListing.specs, F.data.startswith("deal:"))
@router.callback_query(AddListing.specs, F.data.startswith("ptype:"))
@router.callback_query(AddListing.specs, F.data.startswith("rooms:"))
async def s_specs(cb: CallbackQuery, state: FSMContext) -> None:
    key, value = cb.data.split(":", 1)
    await state.update_data(**{key: int(value) if key == "rooms" else value})
    await cb.answer()
    await _goto(cb.message, state, "specs")


@router.callback_query(AddListing.specs, F.data == "add:next")
async def s_specs_next(cb: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if not data.get("deal") or not data.get("ptype") or not data.get("rooms"):
        await cb.answer("Выбери значение кнопкой ☝️", show_alert=True)
        return
    await cb.answer()
    await _goto(cb.message, state, "district")


# --- step 2: district -------------------------------------------------------

@router.callback_query(AddListing.district, F.data.startswith("district:"))
async def s_district(cb: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(district=cb.data.split(":", 1)[1])
    await cb.answer()
    await _goto(cb.message, state, "price")


# --- step 3: price (typed) --------------------------------------------------

@router.message(AddListing.price)
async def s_price(message: Message, state: FSMContext) -> None:
    txt = _num((message.text or "").replace(" ", "")).replace(",", ".")
    try:
        price = int(float(txt))
        if price <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Введи число, например 450")
        return
    await state.update_data(price=price)
    await _goto(message, state, "area")


# --- step 4: optional details (typed or skipped) ----------------------------

@router.message(AddListing.area)
async def s_area(message: Message, state: FSMContext) -> None:
    try:
        area = float(_num(message.text or "").replace(",", "."))
    except ValueError:
        await message.answer("Введи число, например 55")
        return
    await state.update_data(area=area)
    await _goto(message, state, "floor")


@router.message(AddListing.floor)
async def s_floor(message: Message, state: FSMContext) -> None:
    txt = (message.text or "").strip()
    val = None
    floors = None
    try:
        parts = txt.split("/")
        val = int(parts[0])
        if len(parts) > 1:
            floors = int(parts[1])
    except ValueError:
        pass
    await state.update_data(floor=val, floors=floors)
    await _goto(message, state, "description")


@router.message(AddListing.description)
async def s_desc(message: Message, state: FSMContext) -> None:
    await state.update_data(description=(message.text or "")[:600])
    await _goto(message, state, "phone")


@router.message(AddListing.phone)
async def s_phone(message: Message, state: FSMContext) -> None:
    await state.update_data(phone=(message.text or "").strip()[:25])
    await _goto(message, state, "photos")


@router.callback_query(AddListing.area, F.data == "skip:next")
@router.callback_query(AddListing.floor, F.data == "skip:next")
@router.callback_query(AddListing.description, F.data == "skip:next")
@router.callback_query(AddListing.phone, F.data == "skip:next")
async def s_skip(cb: CallbackQuery, state: FSMContext) -> None:
    cur = (await state.get_state() or "").split(":")[-1]
    await cb.answer()
    await _goto(cb.message, state, SKIP_NEXT[cur])


# --- step 5: photos ---------------------------------------------------------

@router.message(AddListing.photos, F.photo)
async def s_photo(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    photos = list(data.get("photos") or [])
    if len(photos) >= 10:
        await message.answer("Максимум 10 фото.")
        return
    photos.append(message.photo[-1].file_id)
    await state.update_data(photos=photos)
    await message.answer(f"Добавлено фото: {len(photos)}. Ещё или «Готово».")


@router.message(AddListing.photos, F.document)
async def s_photo_doc(message: Message) -> None:
    # самая частая случайная дыра: фото уходит как «файл» и мастер молчит
    await message.answer(
        "Это пришло как <b>файл</b>, а мне нужно фото — отправь его без галочки «обычный файл» "
        "(тогда оно встанет в карточку объекта). Или нажми «Пропустить» ⏭.",
        parse_mode="HTML",
    )


@router.message(AddListing.photos)
async def s_photos_other(message: Message) -> None:
    await message.answer("Отправь фото (1–10), затем «Готово». Или сразу «Пропустить» ⏭.")


@router.callback_query(AddListing.photos, F.data == "add:photos_skip")
async def s_photos_skip(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await _goto(cb.message, state, "confirm")


@router.callback_query(AddListing.photos, F.data == "add:photos_done")
async def s_photos_done(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await _goto(cb.message, state, "confirm")


# --- back / cancel / text guards --------------------------------------------

@router.callback_query(F.data == "add:back")
async def s_back(cb: CallbackQuery, state: FSMContext) -> None:
    """One step back along the spine, every answered value preserved. Outside the wizard
    (a stale button from an old message) it is a no-op, not a state corruption."""
    cur = (await state.get_state() or "").split(":")[-1]
    if cur not in STEP_ORDER or cur == "specs":
        await cb.answer()
        return
    prev = STEP_ORDER[STEP_ORDER.index(cur) - 1]
    await cb.answer()
    await _goto(cb.message, state, prev)


@router.message(AddListing.specs)
@router.message(AddListing.district)
@router.message(AddListing.confirm)
async def s_need_button(message: Message) -> None:
    # иначе любой текст посреди мастера проваливается в support-fallback и улетает админам
    await message.answer("Выбери вариант кнопкой 👇 — «⬅️ Назад» вернёт шаг назад, «✖️ Отмена» выйдет.")


def _summary(data: dict) -> str:
    deal = DEAL_LABELS.get(data.get("deal"), "?")
    ptype = PTYPE_LABELS.get(data.get("ptype"), "?")
    lines = [
        "<b>Проверь объявление:</b>",
        f"Тип: {deal} · {ptype}",
        f"Комнат: {data.get('rooms')}",
        f"Район: {html.escape(str(data.get('district')))}",
        f"Цена: <b>{data.get('price')} {data.get('currency', 'EUR')}</b>",
    ]
    if data.get("area"):
        lines.append(f"Площадь: {data.get('area')} м²")
    if data.get("floor"):
        floors = f"/{data['floors']}" if data.get("floors") else ""
        lines.append(f"Этаж: {data.get('floor')}{floors}")
    if data.get("description"):
        lines.append(f"Описание: {html.escape(str(data.get('description')))}")
    lines.append(f"Телефон: {html.escape(str(data.get('phone') or '—'))}")
    lines.append(f"Фото: {len(data.get('photos') or [])}")
    return "\n".join(lines)


@router.callback_query(AddListing.confirm, F.data == "add:confirm")
async def s_confirm(cb: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    user = await db.get_or_create_user(cb.from_user.id, cb.from_user.username, cb.from_user.first_name)
    listing_id = await db.create_listing(
        user_id=user["id"],
        deal=data.get("deal"),
        ptype=data.get("ptype"),
        rooms=data.get("rooms"),
        price=data.get("price"),
        currency="EUR",
        district=data.get("district"),
        area=data.get("area"),
        floor=data.get("floor"),
        floors=data.get("floors"),
        phone=data.get("phone") or user["phone"],
        description=data.get("description"),
        photos=data.get("photos", []),
    )
    if data.get("phone"):
        await db.set_user_phone(user["id"], data["phone"])
    await db.log_event("listing_created", user_id=user["id"], listing_id=listing_id)
    await state.clear()
    await cb.answer("Отправлено на модерацию")
    text = (
        f"✅ Объявление <b>#{listing_id}</b> отправлено на модерацию.\n"
        "После проверки оно появится в поиске."
    )
    try:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=keyboards.main_menu())
    except Exception:
        await cb.message.answer(text, parse_mode="HTML", reply_markup=keyboards.main_menu())
    await _notify_admins(bot, listing_id)


async def _notify_admins(bot: Bot, listing_id: int) -> None:
    row = await db.get_listing(listing_id)
    if not row:
        return
    caption = f"🆕 <b>Новое объявление на модерацию</b>\n\n" + _summary({
        "deal": row["deal"], "ptype": row["ptype"], "rooms": row["rooms"],
        "district": row["district"], "price": row["price"], "currency": row["currency"],
        "area": row["area"], "floor": row["floor"], "floors": row["floors"],
        "description": row["description"],
        "phone": row["phone"], "photos": db.listing_photos(row),
    })
    for admin in config.ADMIN_IDS:
        try:
            await bot.send_message(admin, caption, parse_mode="HTML",
                                   reply_markup=keyboards.moderation_kb(listing_id))
        except Exception:
            pass
