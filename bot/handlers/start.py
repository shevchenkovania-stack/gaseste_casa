from aiogram import F, Router
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import config
import db
import keyboards
from handlers import add as add_h
from handlers import boost as boost_h

router = Router()

WELCOME = (
    "Привет! \U0001F3E0 Это <b>ChirieBot</b> — аренда и продажа недвижимости в Кишинёве.\n\n"
    "Найди жильё или размести своё объявление.\n"
    "\U0001F916 Размещение <b>бесплатное</b>. Хочешь выделиться — подними объявление через Boost."
)


async def show_menu(target: Message, first_name: str | None = None) -> None:
    text = WELCOME if first_name else "Главное меню:"
    await target.answer(text, parse_mode="HTML", reply_markup=keyboards.main_menu())


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    u = await db.get_or_create_user(
        message.from_user.id, message.from_user.username, message.from_user.first_name
    )
    await db.log_event("start", user_id=u["id"])
    await show_menu(message, message.from_user.first_name)


@router.message(F.text.startswith("/startapp boost:"))
async def deep_boost(message: Message) -> None:
    """Deep link from the Mini App: /startapp boost:<listing_id>."""
    try:
        listing_id = int(message.text.split("boost:", 1)[1].split()[0])
    except (ValueError, IndexError):
        return
    await boost_h.offer_flow(message, message.from_user, listing_id)


@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    await show_menu(message)


@router.callback_query(F.data == "menu:home")
async def cb_home(cb: CallbackQuery) -> None:
    await cb.answer()
    await cb.message.answer("Главное меню:", reply_markup=keyboards.main_menu())


@router.callback_query(F.data == "menu:help")
async def cb_help(cb: CallbackQuery) -> None:
    await cb.answer()
    text = (
        "<b>Как это работает</b>\n\n"
        "\U0001F50D <b>Поиск</b> — найти аренду или продажу.\n"
        "\u2795 <b>Разместить объект</b> — добавить своё объявление (бесплатно).\n"
        "\U0001F4CB <b>Мои объявления</b> — управлять своими объектами и поднимать их.\n\n"
        "\U0001F680 <b>Boost</b> — платное поднятие объявления в топ выдачи.\n"
        "Оплата Telegram Stars \u2B50 (быстро и безопасно).\n\n"
        "Объявления проходят короткую модерацию."
    )
    await cb.message.answer(text, parse_mode="HTML", reply_markup=keyboards.back_menu())


@router.callback_query(F.data == "menu:add")
async def cb_add(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await add_h.begin(cb.message, state)


@router.message(Command("paysupport"))
async def cmd_paysupport(message: Message) -> None:
    import config
    contact = config.CONTACT_URL or "@support"
    await message.answer(
        f"Вопросы и возвраты по оплате (Telegram Stars): {contact}",
        reply_markup=keyboards.back_menu(),
    )


@router.callback_query(F.data == "cancel")
async def cb_cancel(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await cb.answer("Отменено")
    await cb.message.answer("Действие отменено.", reply_markup=keyboards.main_menu())
