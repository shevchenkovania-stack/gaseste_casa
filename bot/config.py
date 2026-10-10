import os
from dotenv import load_dotenv

load_dotenv()


def _admins(raw: str):
    out = []
    for x in raw.replace(" ", "").split(","):
        if x.strip().lstrip("-").isdigit():
            out.append(int(x))
    return out


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = _admins(os.getenv("ADMIN_IDS", ""))

DB_PATH = os.getenv("DB_PATH", "/opt/imobiliare/data/imobiliare.db")
PHOTOS_DIR = os.getenv("PHOTOS_DIR", "/opt/imobiliare/data/photos")

DEFAULT_CURRENCY = os.getenv("DEFAULT_CURRENCY", "EUR")

BOOST_STARS = int(os.getenv("BOOST_STARS", "50"))
BOOST_DAYS = int(os.getenv("BOOST_DAYS", "7"))

CONTACT_URL = os.getenv("CONTACT_URL", "")

# Telegram Stars currency code; 1 Star ~= 1 cent. For digital goods inside Telegram.
STARS_CURRENCY = "XTR"
