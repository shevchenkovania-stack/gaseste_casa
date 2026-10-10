"""Publishing approved listings: download photos for Mini App + post to public channel."""
import os

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto

import config
import db
import render

MAX_PHOTOS = 10


async def download_photos(bot: Bot, row) -> None:
    """Save listing photos as {listing_id}_{i}.jpg in PHOTOS_DIR for the webapp."""
    photos = db.listing_photos(row)[:MAX_PHOTOS]
    if not photos:
        return
    os.makedirs(config.PHOTOS_DIR, exist_ok=True)
    for i, file_id in enumerate(photos):
        dest = os.path.join(config.PHOTOS_DIR, f"{row['id']}_{i}.jpg")
        if os.path.exists(dest):
            continue
        try:
            f = await bot.get_file(file_id)
            await bot.download_file(f.file_path, dest)
        except Exception:
            pass  # missing photo only degrades the web card


def contact_kb(row, owner) -> InlineKeyboardMarkup | None:
    rows = []
    if owner and owner["username"]:
        rows.append([InlineKeyboardButton(text="\U0001F4AC Написать в Telegram",
                                         url=f"https://t.me/{owner['username']}")])
    browse_url = config.WEBAPP_URL or config.CHANNEL_URL
    if browse_url:
        rows.append([InlineKeyboardButton(text="\U0001F50D Смотреть все объекты", url=browse_url)])
    if config.BOT_URL:
        rows.append([InlineKeyboardButton(text="\u2795 Разместить своё объявление", url=config.BOT_URL)])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


async def to_channel(bot: Bot, row) -> None:
    if not config.CHANNEL_ID:
        return
    photos = db.listing_photos(row)[:MAX_PHOTOS]
    caption = render.listing_caption(row)
    if row["phone"]:
        caption += f"\n\U0001F4DE {row['phone']}"
    owner = await db.get_user_by_id(row["user_id"])
    kb = contact_kb(row, owner)
    web_photos = [os.path.join(config.PHOTOS_DIR, f"{row['id']}_{i}.jpg")
                  for i in range(min(len(photos), MAX_PHOTOS))
                  if os.path.exists(os.path.join(config.PHOTOS_DIR, f"{row['id']}_{i}.jpg"))]
    if web_photos:
        media = [InputMediaPhoto(media=p, caption=caption if i == 0 else None, parse_mode="HTML")
                 for i, p in enumerate(web_photos)]
        sent = await bot.send_media_group(config.CHANNEL_ID, media)
        msg = await bot.send_message(config.CHANNEL_ID, "↑ контакты и детали ниже", reply_markup=kb)
        ids = [m.message_id for m in sent] + [msg.message_id]
    else:
        msg = await bot.send_message(config.CHANNEL_ID, caption, parse_mode="HTML", reply_markup=kb)
        ids = [msg.message_id]
    await db.log_event("channel_post", listing_id=row["id"], meta=",".join(map(str, ids)))


async def publish_listing(bot: Bot, row) -> None:
    await download_photos(bot, row)
    await to_channel(bot, row)
