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

# Alternative payment rail: bank/card transfer in MDL, confirmed by a human admin.
# Works in Moldova without acquiring contract and without Telegram Stars. 0 -> disabled.
BOOST_MDL = int(os.getenv("BOOST_MDL", "0"))
# Recipient details shown to the buyer, e.g. "card 5199 xxxx xxxx xxxx, maib, Ivan P."
PAY_INFO = os.getenv("PAY_INFO", "").strip()

# Rail 3: real card payment (Visa/Mastercard) through Lemon Squeezy as merchant of record.
# Stripe does not issue merchant accounts in Moldova and local acquiring needs a legal entity;
# LS lists Moldova as a supported bank-payout country and handles VAT/chargebacks itself.
LS_API_KEY = os.getenv("LS_API_KEY", "").strip()
LS_STORE_ID = os.getenv("LS_STORE_ID", "").strip()
LS_VARIANT_ID = os.getenv("LS_VARIANT_ID", "").strip()
# Signing secret from LS Settings -> Webhooks; the X-Signature header is HMAC-SHA256 of the raw body.
LS_WEBHOOK_SECRET = os.getenv("LS_WEBHOOK_SECRET", "").strip()
# Price of one Boost in US cents on the LS checkout (store currency). 500 = $5.00 ~ 90 MDL.
CARD_PRICE_CENTS = int(os.getenv("CARD_PRICE_CENTS", "500"))
# Button appears only when the store is actually wired up; webhook needs the secret too.
CARD_ENABLED = bool(LS_API_KEY and LS_STORE_ID and LS_VARIANT_ID)

# Revenue loop: remind owners of unboosted active listings to buy a Boost.
NUDGE_AFTER_DAYS = int(os.getenv("NUDGE_AFTER_DAYS", "2"))
NUDGE_COOLDOWN_DAYS = int(os.getenv("NUDGE_COOLDOWN_DAYS", "4"))
NUDGE_INTERVAL_HOURS = int(os.getenv("NUDGE_INTERVAL_HOURS", "6"))

CONTACT_URL = os.getenv("CONTACT_URL", "")

# Public channel where approved listings are auto-posted (@username or -100... chat id)
CHANNEL_ID = os.getenv("CHANNEL_ID", "").strip() or None
# t.me link derived from CHANNEL_ID when it is a public @username (empty otherwise)
CHANNEL_URL = f"https://t.me/{CHANNEL_ID[1:]}" if CHANNEL_ID and CHANNEL_ID.startswith("@") else ""
# HTTPS URL of the Telegram Mini App (webapp/). Empty -> app button hidden.
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()
# Public username, used for "post your own listing" CTAs in channel posts.
BOT_USERNAME = os.getenv("BOT_USERNAME", "").strip()
BOT_URL = f"https://t.me/{BOT_USERNAME}" if BOT_USERNAME else ""

# Telegram Stars currency code; 1 Star ~= 1 cent. For digital goods inside Telegram.
STARS_CURRENCY = "XTR"
