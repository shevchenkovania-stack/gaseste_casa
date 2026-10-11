import html
import re

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import config
import db
import keyboards
from constants import DEAL_LABELS, DISTRICTS, PTYPE_LABELS, ROOMS

router = Router()


class AddListing(StatesGroup):
    deal = State()
    ptype = State()
    rooms = State()
    district = State()
    price = State()
    area = State()
    floor = State()
    description = State()
    phone = State()
    photos = State()
    confirm = State()


def photos_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\u2705 Готово", callback_data="add:photos_done")],
        [InlineKeyboardButton(text="Пропустить \u23ED", callback_data="add:photos_skip")],
        [InlineKeyboardButton(text="\u2b05\uFE0F Отмена", callback_data="cancel")],
    ])


async def begin(message: Message, state: FSMContext) -> None:
    await state.set_state(AddListing.deal)
    await message.answer("Шаг 1/8. Что делаем с объектом?", reply_markup=keyboards.deal_kb())


@router.callback_query(AddListing.deal, F.data.startswith("deal:"))
async def s_deal(cb: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(deal=cb.data.split(":", 1)[1])
    await state.set_state(AddListing.ptype)
    await cb.answer()
    await cb.message.answer("Шаг 2/8. Тип объекта?", reply_markup=keyboards.ptype_kb())


@router.callback_query(AddListing.ptype, F.data.startswith("ptype:"))
async def s_ptype(cb: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(ptype=cb.data.split(":", 1)[1])
    await state.set_state(AddListing.rooms)
    await cb.answer()
    await cb.message.answer("Шаг 3/8. Количество комнат?", reply_markup=keyboards.options_kb("rooms", ROOMS))


@router.callback_query(AddListing.rooms, F.data.startswith("rooms:"))
async def s_rooms(cb: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(rooms=int(cb.data.split(":", 1)[1]))
    await state.set_state(AddListing.district)
    await cb.answer()
    await cb.message.answer("Шаг 4/8. Район?", reply_markup=keyboards.districts_kb())


@router.callback_query(AddListing.district, F.data.startswith("district:"))
async def s_district(cb: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(district=cb.data.split(":", 1)[1])
    await state.set_state(AddListing.price)
    await cb.answer()
    await cb.message.answer("Шаг 5/8. Цена (числом, валюта EUR):\nнапример <code>450</code>", parse_mode="HTML")


def _num(txt: str) -> str:
    """Оставить только цифры и разделители: '450 eur', '450€', '450 €' -> '450'.
    Люди вписывают валюту и символы в поле цены - не надо гонять их с начала."""
    return re.sub(r"[^\d.,]", "", txt or "")


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
    await state.set_state(AddListing.area)
    await message.answer("Шаг 6/8. Площадь, м² (или Пропустить):", reply_markup=keyboards.skip_kb("area"))


@router.callback_query(AddListing.area, F.data == "area:skip")
async def s_area_skip(cb: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(area=None)
    await state.set_state(AddListing.floor)
    await cb.answer()
    await cb.message.answer("Этаж (или Пропустить):", reply_markup=keyboards.skip_kb("floor"))


@router.message(AddListing.area)
async def s_area(message: Message, state: FSMContext) -> None:
    try:
        area = float(_num(message.text or "").replace(",", "."))
    except ValueError:
        await message.answer("Введи число, например 55")
        return
    await state.update_data(area=area)
    await state.set_state(AddListing.floor)
    await message.answer("Этаж (или Пропустить):", reply_markup=keyboards.skip_kb("floor"))


@router.callback_query(AddListing.floor, F.data == "floor:skip")
async def s_floor_skip(cb: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(floor=None, floors=None)
    await state.set_state(AddListing.description)
    await cb.answer()
    await cb.message.answer("Описание (или Пропустить):", reply_markup=keyboards.skip_kb("desc"))


@router.message(AddListing.floor)
async def s_floor(message: Message, state: FSMContext) -> None:
    txt = (message.text or "").strip()
    val = None
    try:
        val = int(txt.split("/")[0])
    except ValueError:
        pass
    await state.update_data(floor=val)
    await state.set_state(AddListing.description)
    await message.answer("Описание (или Пропустить):", reply_markup=keyboards.skip_kb("desc"))


@router.callback_query(AddListing.description, F.data == "desc:skip")
async def s_desc_skip(cb: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(description=None)
    await state.set_state(AddListing.phone)
    await cb.answer()
    await cb.message.answer("Контактный телефон (или Пропустить):", reply_markup=keyboards.skip_kb("phone"))


@router.message(AddListing.description)
async def s_desc(message: Message, state: FSMContext) -> None:
    await state.update_data(description=(message.text or "")[:600])
    await state.set_state(AddListing.phone)
    await message.answer("Контактный телефон (или Пропустить):", reply_markup=keyboards.skip_kb("phone"))


@router.callback_query(AddListing.phone, F.data == "phone:skip")
async def s_phone_skip(cb: CallbackQuery, state: FSMContext) -> None:
    await _to_photos(cb, state)


@router.message(AddListing.phone)
async def s_phone(message: Message, state: FSMContext) -> None:
    await state.update_data(phone=(message.text or "").strip()[:25])
    await state.set_state(AddListing.photos)
    await state.update_data(photos=[])
    await message.answer(
        "Фото объекта: отправь 1–10 фото, затем нажми Готово:",
        reply_markup=photos_kb(),
    )


async def _to_photos(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddListing.photos)
    await state.update_data(photos=[])
    await cb.answer()
    await cb.message.answer(
        "Фото объекта: отправь 1–10 фото, затем нажми Готово:",
        reply_markup=photos_kb(),
    )


@router.message(AddListing.photos, F.photo)
async def s_photo(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    photos = data.get("photos", [])
    if len(photos) >= 10:
        await message.answer("Максимум 10 фото.")
        return
    photos.append(message.photo[-1].file_id)
    await state.update_data(photos=photos)
    await message.answer(f"Добавлено фото: {len(photos)}. Ещё или Готово.")


@router.callback_query(AddListing.photos, F.data == "add:photos_skip")
async def s_photos_skip(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await _show_confirm(cb.message, state)


@router.callback_query(AddListing.photos, F.data == "add:photos_done")
async def s_photos_done(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await _show_confirm(cb.message, state)


@router.message(AddListing.photos, F.document)
async def s_photo_doc(message: Message) -> None:
    # самая частая случайная дыра: фото уходит как «файл» и мастер молчит
    await message.answer(
        "Это пришло как <b>файл</b>, а мне нужно фото — отправь его без галочки «обычное файл» "
        "(тогда оно встанет в карточку объекта). Или нажми «Пропустить» \u23ED.",
        parse_mode="HTML",
    )


@router.message(AddListing.photos)
async def s_photos_other(message: Message) -> None:
    await message.answer("Отправь фото (1–10), затем «Готово». Или сразу «Пропустить» \u23ED.")


@router.message(AddListing.deal)
@router.message(AddListing.ptype)
@router.message(AddListing.rooms)
@router.message(AddListing.district)
@router.message(AddListing.confirm)
async def s_need_button(message: Message) -> None:
    # иначе любой текст посреди мастера проваливается в support-fallback и улетает админам
    await message.answer("Выбери вариант кнопкой \U0001F446 Отменить мастер — кнопка «⬅️ Отмена».")


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
        lines.append(f"Этаж: {data.get('floor')}")
    if data.get("description"):
        lines.append(f"Описание: {html.escape(str(data.get('description')))}")
    lines.append(f"Телефон: {html.escape(str(data.get('phone') or '—'))}")
    lines.append(f"Фото: {len(data.get('photos', []))}")
    return "\n".join(lines)


async def _show_confirm(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.set_state(AddListing.confirm)
    await message.answer(_summary(data), parse_mode="HTML", reply_markup=keyboards.confirm_kb())


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
    await cb.message.answer(
        f"\u2705 Объявление <b>#{listing_id}</b> отправлено на модерацию.\n"
        "После проверки оно появится в поиске.",
        parse_mode="HTML",
        reply_markup=keyboards.main_menu(),
    )
    await _notify_admins(bot, listing_id)


async def _notify_admins(bot: Bot, listing_id: int) -> None:
    row = await db.get_listing(listing_id)
    if not row:
        return
    caption = f"\U0001F195 <b>Новое объявление на модерацию</b>\n\n" + _summary({
        "deal": row["deal"], "ptype": row["ptype"], "rooms": row["rooms"],
        "district": row["district"], "price": row["price"], "currency": row["currency"],
        "area": row["area"], "floor": row["floor"], "description": row["description"],
        "phone": row["phone"], "photos": db.listing_photos(row),
    })
    for admin in config.ADMIN_IDS:
        try:
            await bot.send_message(admin, caption, parse_mode="HTML",
                                   reply_markup=keyboards.moderation_kb(listing_id))
        except Exception:
            pass
