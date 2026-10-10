"""Put the Mini App into the bot's chat menu button — Bot API, no @BotFather session needed.

The RUNBOOK used to call this a human step. It is not: setChatMenuButton does exactly what the
BotFather menu does, and it needs only WEBAPP_URL, which apply_tunnel.sh / apply_https.sh already
maintain. Re-run it after the tunnel address changes, otherwise the button opens a dead host.

Run: cd /opt/imobiliare/bot && /opt/imobiliare/venv/bin/python /tmp/set_menu_button.py
"""
import asyncio
import sys

sys.path.insert(0, "/opt/imobiliare/bot")

from aiogram import Bot
from aiogram.types import MenuButtonWebApp, WebAppInfo

import config

TEXT = "\U0001F3E0 Искать квартиры"


async def main() -> None:
    if not config.WEBAPP_URL:
        sys.exit("WEBAPP_URL пуст — сначала bash /tmp/apply_tunnel.sh (или apply_https.sh <домен>)")
    if not config.WEBAPP_URL.startswith("https://"):
        sys.exit(f"WEBAPP_URL должен быть HTTPS, а он {config.WEBAPP_URL}")
    bot = Bot(config.BOT_TOKEN)
    # No chat_id -> the default for all private chats, which is exactly where buyers land.
    await bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(text=TEXT, web_app=WebAppInfo(url=config.WEBAPP_URL))
    )
    got = await bot.get_chat_menu_button()
    url = getattr(getattr(got, "web_app", None), "url", None)
    await bot.session.close()
    print("menu button type:", type(got).__name__)
    print("menu button text:", getattr(got, "text", None))
    print("menu button url:", url)
    # Telegram normalises the URL: it appends the trailing slash. Compare the host, not the string.
    if (url or "").rstrip("/") != config.WEBAPP_URL.rstrip("/"):
        sys.exit(f"НЕ совпало: ждали {config.WEBAPP_URL}, Telegram вернул {url}")
    print("OK: кнопка в меню бота ведёт в Mini App")


if __name__ == "__main__":
    asyncio.run(main())
