import asyncio

from aiogram import Bot
from aiogram.types import FSInputFile
from PIL import Image, ImageDraw, ImageFont

import config
import db

ADMIN_TG = 1182157446

SAMPLES = [
    dict(deal="rent", ptype="apartment", rooms=2, price=500, district="Ботаника", area=60,
         floor=5, floors=9, phone="+373 60 111 222",
         description="Светлая 2-комнатная в Ботанике, новый ремонт, мебель и техника. Рядом парк и школа.",
         imgs=[("#0f766e", "2 комнаты · Ботаника", "60 м² · 500 EUR"),
               ("#115e59", "Гостиная", "светлая, меблирована"),
               ("#134e4a", "Кухня", "техника в наличии")]),
    dict(deal="rent", ptype="apartment", rooms=1, price=400, district="Центр", area=45,
         floor=3, floors=5, phone="+373 60 111 223",
         description="1-комнатная в центре, полностью меблированная, рядом Steaua Roșie. Для одного/пары.",
         imgs=[("#1d4ed8", "1 комната · Центр", "45 м² · 400 EUR"),
               ("#1e40af", "Комната", "уютная, меблирована")]),
    dict(deal="rent", ptype="house", rooms=4, price=900, district="Кодры", area=140,
         floor=1, floors=2, phone="+373 60 111 224",
         description="Дом в Кодрах, 4 комнаты, большой участок, гараж. Долгосрочная аренда.",
         imgs=[("#7c3aed", "Дом · Кодры", "140 м² · 900 EUR"),
               ("#6d28d9", "Фасад", "участок, гараж")]),
]


def make_image(color: str, title: str, subtitle: str, path: str) -> None:
    W, H = 800, 600
    img = Image.new("RGB", (W, H), color)
    d = ImageDraw.Draw(img)
    try:
        f1 = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
        f2 = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 32)
    except OSError:
        f1 = ImageFont.load_default()
        f2 = ImageFont.load_default()
    d.rectangle((30, 30, W - 30, H - 30), outline=(255, 255, 255), width=4)
    bbox = d.textbbox((0, 0), title, font=f1)
    d.text(((W - (bbox[2] - bbox[0])) / 2, H / 2 - 70), title, fill="white", font=f1)
    bbox2 = d.textbbox((0, 0), subtitle, font=f2)
    d.text(((W - (bbox2[2] - bbox2[0])) / 2, H / 2 + 10), subtitle, fill="white", font=f2)
    d.text((40, H - 70), "Găsește Casa (demo)", fill=(255, 255, 255), font=f2)
    img.save(path)


async def main() -> None:
    await db.init_db()
    user = await db.get_or_create_user(ADMIN_TG, "JohnRockSh", "Иван")
    bot = Bot(token=config.BOT_TOKEN)
    created = []
    for idx, s in enumerate(SAMPLES, 1):
        file_ids = []
        for j, (color, title, sub) in enumerate(s["imgs"], 1):
            path = f"/tmp/seed_{idx}_{j}.png"
            make_image(color, title, sub, path)
            msg = await bot.send_photo(ADMIN_TG, FSInputFile(path),
                                       caption=f"\U0001F4F8 Тест-фото к объявлению #{idx}")
            file_ids.append(msg.photo[-1].file_id)
        data = {k: v for k, v in s.items() if k != "imgs"}
        lid = await db.create_listing(user_id=user["id"], photos=file_ids, **data)
        await db.set_listing_status(lid, "active")
        created.append(lid)
        await asyncio.sleep(0.3)
    print("CREATED_LISTINGS", created)
    print("STATS", await db.stats())
    await db.close_db()
    await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
