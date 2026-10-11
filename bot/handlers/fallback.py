import logging

from aiogram import Bot, F, Router
from aiogram.types import Message

import config
import keyboards

log = logging.getLogger("chiriebot.fallback")

router = Router()


@router.message(F.text, ~F.text.startswith("/"))
async def forward_to_admins(message: Message, bot: Bot) -> None:
    """A real support line: plain text a user types that no other router handled gets forwarded to
    the admins, so "write us in this chat" is true instead of a dead @support handle. This router is
    included LAST, so the add-listing wizard (whose steps are registered in add.router with an active
    FSM state) matches its own text inputs first - a fallback never steals a wizard answer.
    """
    who = f"@{message.from_user.username}" if message.from_user.username else str(message.from_user.id)
    for admin in config.ADMIN_IDS:
        try:
            await bot.send_message(admin, f"\U0001F4AC Сообщение от {who}:\n{message.text}")
        except Exception:
            pass
    log.info("user message forwarded to %d admin(s) from %s", len(config.ADMIN_IDS), who)
    await message.answer(
        "Передал модератору \U0001F44C Ответим в этом чате в рабочее время.",
        reply_markup=keyboards.back_menu(),
    )
