import asyncio

from aiogram import Bot

import config
import db
import render

ADMIN_TG = 1182157446


async def main() -> None:
    await db.init_db()
    bot = Bot(token=config.BOT_TOKEN)
    rows = await db.search_listings(limit=10)
    await bot.send_message(ADMIN_TG, f"\U0001F50D Поиск вернул {len(rows)} объявлений. Ниже — как они выглядят:")
    for r in rows:
        await render.send_listing(bot, ADMIN_TG, r, owner=True)
        await asyncio.sleep(0.6)
    await bot.send_message(ADMIN_TG, "\u2705 Тест рендеринга завершён. Проверь также кнопки в карточках.")
    await db.close_db()
    await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
