"""Lemon Squeezy as merchant of record: real Visa/Mastercard payments for a Moldovan seller.

Why this provider: Stripe does not issue merchant accounts in Moldova and local acquiring
(maib pay, bpay) requires a legal entity, while LS lists Moldova among supported bank payout
countries and sells to the customer as the merchant of record (their problem: VAT, chargebacks,
card declines). Fee is ~5% + payout, no monthly fee, no entity needed.

Only three things touch the outside world:
  create_checkout()    - POST /v1/checkouts, returns a hosted payment link for one listing
  verify_signature()   - HMAC-SHA256 of the raw webhook body (X-Signature header)
  parse_order_event()  - reads a webhook order payload into our own row shape
Money is never moved or credited here: the webhook only stores the order, the bot applies it.
"""
import datetime as dt
import hashlib
import hmac
import json

import aiohttp

import config

API = "https://api.lemonsqueezy.com/v1"
JSONAPI = {"Accept": "application/vnd.api+json", "Content-Type": "application/vnd.api+json"}


def verify_signature(raw_body: bytes, signature: str) -> bool:
    """LS signs the raw request body: hex HMAC-SHA256 with the webhook signing secret."""
    if not config.LS_WEBHOOK_SECRET or not signature:
        return False
    expected = hmac.new(config.LS_WEBHOOK_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip())


async def create_checkout(listing_id: int, tg_id: int, expires_minutes: int = 180) -> tuple[str, str]:
    """Create a single-use hosted checkout. Returns (checkout_uuid, url).

    Our ids ride along in checkout_data.custom and come back in meta.custom_data of the
    webhook, which is how a paid order is mapped to a listing without any public page of ours.
    """
    expires = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=expires_minutes)
    payload = {
        "data": {
            "type": "checkouts",
            "attributes": {
                "custom_price": config.CARD_PRICE_CENTS,
                "product_options": {
                    "name": f"Boost объявления #{listing_id} ({config.BOOST_DAYS} дней)",
                    "enabled_variants": [int(config.LS_VARIANT_ID)],
                },
                "checkout_options": {"discount": False, "media": False},
                "checkout_data": {"custom": {"listing_id": listing_id, "tg_id": tg_id}},
                "expires_at": expires.strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
            "relationships": {
                "store": {"data": {"type": "stores", "id": str(config.LS_STORE_ID)}},
                "variant": {"data": {"type": "variants", "id": str(config.LS_VARIANT_ID)}},
            },
        }
    }
    headers = dict(JSONAPI, Authorization=f"Bearer {config.LS_API_KEY}")
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
        async with session.post(f"{API}/checkouts", json=payload, headers=headers) as resp:
            data = await resp.json()
            if resp.status != 201:
                raise RuntimeError(f"LS checkout {resp.status}: {str(data)[:300]}")
            return data["data"]["id"], data["data"]["attributes"]["url"]


def _as_dict(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except ValueError:
            return {}
    return {}


def parse_order_event(event: dict) -> dict | None:
    """Turn an LS webhook body into a card_orders row. None if it is not a usable order.

    Payload shape (per docs): meta.event_name, meta.custom_data, data.attributes = order object.
    """
    if not isinstance(event, dict):
        return None
    meta = _as_dict(event.get("meta"))
    if meta.get("event_name") not in ("order_created", "order_processed", "order_refunded"):
        return None
    data = _as_dict(event.get("data"))
    attrs = _as_dict(data.get("attributes"))
    custom = _as_dict(meta.get("custom_data"))
    order_id = str(attrs.get("identifier") or data.get("id") or "")
    if not order_id:
        return None
    try:
        amount = int(attrs.get("total") or 0)
    except (TypeError, ValueError):
        amount = 0
    item = _as_dict(attrs.get("first_order_item"))
    return {
        "order_id": order_id,
        "listing_id": int(custom["listing_id"]) if str(custom.get("listing_id", "")).isdigit() else None,
        "tg_id": int(custom["tg_id"]) if str(custom.get("tg_id", "")).isdigit() else None,
        "amount_cents": amount,
        "currency": str(attrs.get("currency") or "USD"),
        "status": str(attrs.get("status") or "pending"),
        "test_mode": bool(attrs.get("test_mode") or item.get("test_mode")),
        "customer": str(attrs.get("user_email") or attrs.get("user_name") or "") or None,
    }
