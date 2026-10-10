from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

import config
from constants import DEAL_LABELS, PTYPE_LABELS

RENT = "\U0001F3E0 Аренда"
SALE = "\U0001F4B0 Продажа"
ADD = "\u2795 Разместить объект"
MY = "\U0001F4CB Мои объявления"
SEARCH = "\U0001F50D Поиск"
HELP = "\u2139\uFE0F Помощь"


def main_menu() -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton(text=SEARCH, callback_data="menu:search")],
        [InlineKeyboardButton(text=ADD, callback_data="menu:add")],
        [InlineKeyboardButton(text=MY, callback_data="menu:my")],
        [InlineKeyboardButton(text=HELP, callback_data="menu:help")],
    ]
    if config.WEBAPP_URL:
        kb.insert(1, [InlineKeyboardButton(text="\U0001F5FA\uFE0F Открыть приложение", web_app=WebAppInfo(url=config.WEBAPP_URL))])
    if config.CHANNEL_URL:
        kb.append([InlineKeyboardButton(text="\U0001F4E3 Канал с объектами", url=config.CHANNEL_URL)])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def deal_kb(prefix: str = "deal") -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=v, callback_data=f"{prefix}:{k}")] for k, v in DEAL_LABELS.items()]
    rows.append([InlineKeyboardButton(text="\u2b05\uFE0F Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def ptype_kb(prefix: str = "ptype") -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=v, callback_data=f"{prefix}:{k}")] for k, v in PTYPE_LABELS.items()]
    rows.append([InlineKeyboardButton(text="\u2b05\uFE0F Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def options_kb(prefix: str, options: list, back: str | None = "cancel") -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=str(o), callback_data=f"{prefix}:{o}")] for o in options]
    if back:
        rows.append([InlineKeyboardButton(text="\u2b05\uFE0F Отмена", callback_data=back)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def districts_kb(prefix: str = "district") -> InlineKeyboardMarkup:
    from constants import DISTRICTS
    rows = []
    pair: list[InlineKeyboardButton] = []
    for d in DISTRICTS:
        pair.append(InlineKeyboardButton(text=d, callback_data=f"{prefix}:{d}"))
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)
    rows.append([InlineKeyboardButton(text="\u2b05\uFE0F Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\u2705 Опубликовать", callback_data="add:confirm")],
        [InlineKeyboardButton(text="\u2b05\uFE0F Отмена", callback_data="cancel")],
    ])


def skip_kb(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пропустить \u23ED", callback_data=f"{prefix}:skip")],
        [InlineKeyboardButton(text="\u2b05\uFE0F Отмена", callback_data="cancel")],
    ])


def listing_kb(listing_id: int, owner: bool, boosted: bool) -> InlineKeyboardMarkup:
    rows = []
    if owner:
        rows.append([InlineKeyboardButton(text="\U0001F680 Поднять (Boost)", callback_data=f"boost:{listing_id}")])
    rows.append([InlineKeyboardButton(text="\U0001F4DE Показать контакт", callback_data=f"contact:{listing_id}")])
    rows.append([InlineKeyboardButton(text="\u2b05\uFE0F К списку", callback_data="back:search")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def boost_kb(listing_id: int, stars: int, days: int, mdl: int = 0) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"\u2B50 Оплатить {stars} Stars", callback_data=f"boostpay:{listing_id}")]]
    if mdl:
        rows.append([InlineKeyboardButton(text=f"\U0001F4B0 Переводом {mdl} MDL", callback_data=f"manual:{listing_id}")])
    rows.append([InlineKeyboardButton(text="\u2b05\uFE0F Назад", callback_data=f"view:{listing_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def manual_kb(listing_id: int, mdl: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"\U0001F4B0 Я перевёл {mdl} MDL", callback_data=f"manualpaid:{listing_id}")],
        [InlineKeyboardButton(text="\u2b05\uFE0F Назад", callback_data=f"view:{listing_id}")],
    ])


def manual_review_kb(boost_id: int, listing_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="\u2705 Деньги пришли", callback_data=f"manapp:{boost_id}"),
            InlineKeyboardButton(text="\u274C Не вижу платежа", callback_data=f"manrej:{boost_id}"),
        ],
        [InlineKeyboardButton(text="\U0001F441 Объявление", callback_data=f"view:{listing_id}")],
    ])


def moderation_kb(listing_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="\u2705 Одобрить", callback_data=f"mod:approve:{listing_id}"),
            InlineKeyboardButton(text="\u274C Отклонить", callback_data=f"mod:reject:{listing_id}"),
        ],
        [InlineKeyboardButton(text="\U0001F441 Показать", callback_data=f"view:{listing_id}")],
    ])


def back_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\U0001F3E0 Меню", callback_data="menu:home")],
    ])
