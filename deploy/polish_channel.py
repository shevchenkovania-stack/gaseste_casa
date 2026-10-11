"""Channel polish: delete service/test posts, set description. Idempotent."""
import asyncio
import sys

sys.path.insert(0, "/opt/imobiliare/bot")
import config
from aiogram import Bot

DESCRIPTION = (
    "🏠 Аренда и продажа квартир и домов в Кишинёве и пригородах.\n"
    "Размещение бесплатное, контакт владельца на каждом объявлении.\n"
    "Сдать или продать за 2 минуты → t.me/gaseste_casa_bot"
)

# service/test posts to remove; pinned promo (#4) is kept
TO_DELETE = [1, 2, 7, 8]


async def main():
    bot = Bot(token=config.BOT_TOKEN)
    cid = config.CHANNEL_ID
    await bot.set_chat_description(cid, DESCRIPTION)
    print("description set:", DESCRIPTION.replace("\n", " | ")[:120])
    for mid in TO_DELETE:
        try:
            await bot.delete_message(cid, mid)
            print(f"deleted #{mid}")
        except Exception as e:
            print(f"#{mid}: {e}")
    chat = await bot.get_chat(cid)
    print("title:", chat.title)
    print("desc now:", (chat.description or "").replace("\n", " | ")[:120])
    await bot.session.close()


asyncio.run(main())
