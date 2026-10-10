import html

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


def usd(cents: int) -> str:
    """Price label for the card rail (Lemon Squeezy store currency is USD)."""
    return f"${cents / 100:.2f}"


def transfer_word() -> str:
    """How we call the MDL rail: MIA (BNM instant payments) once a phone number is configured."""
    return "MIA" if config.PAY_PHONE else "переводом"


def transfer_button() -> str:
    """Button label for the MDL rail, capitalised the way a button deserves."""
    return f"MIA {config.BOOST_MDL} MDL" if config.PAY_PHONE else f"Перевод {config.BOOST_MDL} MDL"


def pay_lines(listing_id: int) -> list:
    """Fields the buyer enters in their banking app, in the order the bank asks for them.
    The 'Boost #N' line is the comment we look for in the bank statement, so it is always there."""
    lines = []
    if config.PAY_PHONE:
        lines.append(config.PAY_PHONE)
    if config.PAY_NAME:
        lines.append(config.PAY_NAME)
    if config.PAY_INFO:
        lines.append(config.PAY_INFO)
    lines.append(f"Boost #{listing_id}")
    return lines


def pay_block(listing_id: int) -> str:
    """Tap-to-copy block: Telegram copies the whole <code> when the user taps it, so nobody
    retypes a phone number and nobody mistypes the comment we match payments by."""
    return "<code>" + html.escape("\n".join(pay_lines(listing_id))) + "</code>"


def manual_pitch(listing_id: int) -> str:
    """The whole MDL payment instruction, written for a person holding a Moldovan banking app."""
    price = config.BOOST_MDL
    if config.PAY_PHONE:
        who = f", сверь имя получателя: <b>{html.escape(config.PAY_NAME)}</b>." if config.PAY_NAME else \
              ", сверь имя получателя на экране подтверждения."
        return (
            f"\u26A1 <b>Boost за {price} MDL</b> (объявление #{listing_id}, {config.BOOST_DAYS} дней)\n\n"
            "1. В приложении банка открой <b>MIA \u00b7 Мгновенные платежи</b> \u2192 «Перевод P2P».\n"
            f"2. Введи номер получателя и сумму <b>{price} MDL</b>{who}\n"
            "3. Комментарием к переводу напиши текст из блока ниже \u2014 по нему мы найдём "
            "твой платёж за секунды.\n\n"
            f"{pay_block(listing_id)}\n\n"
            "Перевод приходит мгновенно, комиссии для переводящего нет. Как только отправишь \u2014 "
            "нажми «Я перевёл»."
        )
    details = html.escape(config.PAY_INFO) if config.PAY_INFO else "реквизиты пришлёт модератор"
    return (
        f"\U0001F4B0 <b>Boost за {price} MDL</b> (объявление #{listing_id}, {config.BOOST_DAYS} дней)\n\n"
        f"1. Переведи <b>{price} MDL</b>: {details}\n"
        f"   В комментарии укажи номер объявления <b>#{listing_id}</b>.\n"
        "2. Нажми «Я перевёл» \u2014 модератор проверит поступление и поднимет объявление.\n\n"
        "Обычно подтверждение занимает несколько минут в рабочее время."
    )


def manual_reference(listing_id: int) -> str:
    """What the admin must spot in the bank statement for this claim."""
    return f"Boost #{listing_id}"


def rails_line() -> str:
    """Payment options in one line: '$5.00 💳 картой / 100 MDL MIA / 400 Stars ⭐'."""
    opts = []
    if config.CARD_ENABLED:
        opts.append(f"{usd(config.CARD_PRICE_CENTS)} \U0001F4B3 картой")
    if config.BOOST_MDL:
        opts.append(f"{config.BOOST_MDL} MDL \U0001F4B0 {transfer_word()}")
    opts.append(f"{config.BOOST_STARS} Stars \u2B50")
    return " / ".join(opts)


def boost_pitch() -> str:
    """One sentence with every wired-up payment rail. Single source for all price copy."""
    return (f"\U0001F680 <b>Boost</b> \u2014 {rails_line()}: объявление поднимается на первое "
            f"место в поиске на <b>{config.BOOST_DAYS} дней</b>.")


def boost_kb(listing_id: int) -> InlineKeyboardMarkup:
    """All available payment rails, cheapest friction first."""
    rows = []
    if config.CARD_ENABLED:
        # hosted checkout: no card attached to Telegram and no acquiring contract needed
        rows.append([InlineKeyboardButton(text=f"\U0001F4B3 Картой {usd(config.CARD_PRICE_CENTS)}",
                                          callback_data=f"card:{listing_id}")])
    if config.BOOST_MDL:
        # instant transfer in MDL: many sellers in MD have no card attached to Telegram, so they
        # cannot buy Stars at all (PROVIDER_ACCOUNT_INVALID), and there is no acquiring contract
        rows.append([InlineKeyboardButton(text=f"\U0001F4B0 {transfer_button()}",
                                          callback_data=f"manual:{listing_id}")])
    rows.append([InlineKeyboardButton(text=f"\u2B50 Оплатить {config.BOOST_STARS} Stars",
                                      callback_data=f"boostpay:{listing_id}")])
    rows.append([InlineKeyboardButton(text="\u2b05\uFE0F Назад", callback_data=f"view:{listing_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def card_pay_kb(url: str, listing_id: int) -> InlineKeyboardMarkup:
    """Opens the Lemon Squeezy checkout in the in-app browser."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\U0001F517 Открыть оплату картой", url=url)],
        [InlineKeyboardButton(text="\u2b05\uFE0F Назад", callback_data=f"view:{listing_id}")],
    ])


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
