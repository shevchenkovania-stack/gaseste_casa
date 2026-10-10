import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

import config
import db
import scheduler
from handlers import add, admin, boost, browse, profile, start

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("chiriebot")


async def set_commands(bot: Bot) -> None:
    await bot.set_my_commands([
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="menu", description="Меню"),
        BotCommand(command="stats", description="Статистика (админ)"),
    ])


async def main() -> None:
    if not config.BOT_TOKEN:
        raise SystemExit("BOT_TOKEN is not set (create .env)")

    await db.init_db()

    bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    dp.include_router(start.router)
    dp.include_router(add.router)
    dp.include_router(browse.router)
    dp.include_router(profile.router)
    dp.include_router(boost.router)
    dp.include_router(admin.router)

    await set_commands(bot)
    me = await bot.get_me()
    log.info("Bot started: @%s", me.username)

    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, "\u2705 ChirieBot запущен и готов к работе.")
        except Exception:
            pass

    job = None
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        job = asyncio.create_task(scheduler.run(bot))
        await dp.start_polling(bot)
    finally:
        if job is not None:
            job.cancel()
        await db.close_db()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit) as e:
        log.info("Bot stopped: %s", e)
