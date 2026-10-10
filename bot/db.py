import json
from typing import Any, Optional

import aiosqlite

from config import DB_PATH

_conn: Optional[aiosqlite.Connection] = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_id INTEGER UNIQUE NOT NULL,
    username TEXT,
    first_name TEXT,
    phone TEXT,
    is_admin INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    deal TEXT NOT NULL,
    ptype TEXT NOT NULL,
    rooms INTEGER,
    price INTEGER NOT NULL,
    currency TEXT DEFAULT 'EUR',
    district TEXT,
    area REAL,
    floor INTEGER,
    floors INTEGER,
    phone TEXT,
    description TEXT,
    photos TEXT DEFAULT '[]',
    status TEXT DEFAULT 'pending',
    boosted_until TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    views INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_listings_status ON listings(status);
CREATE INDEX IF NOT EXISTS idx_listings_district ON listings(district);

CREATE TABLE IF NOT EXISTS boosts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER NOT NULL REFERENCES listings(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    stars INTEGER NOT NULL,
    days INTEGER NOT NULL,
    status TEXT DEFAULT 'pending',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    listing_id INTEGER,
    purpose TEXT,
    stars INTEGER,
    currency TEXT,
    telegram_charge_id TEXT,
    provider_charge_id TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    user_id INTEGER,
    listing_id INTEGER,
    meta TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
"""


async def init_db() -> None:
    global _conn
    _conn = await aiosqlite.connect(DB_PATH)
    _conn.row_factory = aiosqlite.Row
    await _conn.execute("PRAGMA journal_mode=WAL")
    await _conn.execute("PRAGMA busy_timeout=5000")
    await _conn.execute("PRAGMA foreign_keys=ON")
    await _conn.executescript(SCHEMA)
    await _migrate()
    await _conn.commit()


async def _migrate() -> None:
    """Additive column migrations for tables created before the column existed."""
    assert _conn is not None
    cur = await _conn.execute("PRAGMA table_info(listings)")
    cols = {r["name"] for r in await cur.fetchall()}
    if "nudged_at" not in cols:
        await _conn.execute("ALTER TABLE listings ADD COLUMN nudged_at TEXT")


async def close_db() -> None:
    global _conn
    if _conn is not None:
        await _conn.close()
        _conn = None


def _db() -> aiosqlite.Connection:
    assert _conn is not None, "DB not initialized"
    return _conn


async def get_or_create_user(tg_id: int, username: str | None, first_name: str | None) -> aiosqlite.Row:
    db = _db()
    cur = await db.execute("SELECT * FROM users WHERE tg_id = ?", (tg_id,))
    row = await cur.fetchone()
    if row is None:
        await db.execute(
            "INSERT INTO users (tg_id, username, first_name) VALUES (?, ?, ?)",
            (tg_id, username, first_name),
        )
        await db.commit()
        cur = await db.execute("SELECT * FROM users WHERE tg_id = ?", (tg_id,))
        row = await cur.fetchone()
    else:
        await db.execute(
            "UPDATE users SET username = ?, first_name = ? WHERE tg_id = ?",
            (username, first_name, tg_id),
        )
        await db.commit()
    return row


async def set_user_phone(user_id: int, phone: str) -> None:
    db = _db()
    await db.execute("UPDATE users SET phone = ? WHERE id = ?", (phone, user_id))
    await db.commit()


async def get_user_by_id(user_id: int) -> aiosqlite.Row | None:
    cur = await _db().execute("SELECT * FROM users WHERE id = ?", (user_id,))
    return await cur.fetchone()


async def create_listing(**kw: Any) -> int:
    db = _db()
    cur = await db.execute(
        """INSERT INTO listings
           (user_id, deal, ptype, rooms, price, currency, district, area,
            floor, floors, phone, description, photos, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')""",
        (
            kw["user_id"], kw["deal"], kw["ptype"], kw.get("rooms"), kw["price"],
            kw.get("currency", "EUR"), kw.get("district"), kw.get("area"),
            kw.get("floor"), kw.get("floors"), kw.get("phone"),
            kw.get("description"), json.dumps(kw.get("photos", [])),
        ),
    )
    await db.commit()
    return cur.lastrowid


async def get_listing(listing_id: int) -> aiosqlite.Row | None:
    cur = await _db().execute("SELECT * FROM listings WHERE id = ?", (listing_id,))
    return await cur.fetchone()


async def set_listing_status(listing_id: int, status: str) -> None:
    db = _db()
    await db.execute(
        "UPDATE listings SET status = ?, updated_at = datetime('now') WHERE id = ?",
        (status, listing_id),
    )
    await db.commit()


def listing_photos(row) -> list[str]:
    try:
        return json.loads(row["photos"] or "[]")
    except (TypeError, ValueError):
        return []


async def inc_views(listing_id: int) -> None:
    db = _db()
    await db.execute("UPDATE listings SET views = views + 1 WHERE id = ?", (listing_id,))
    await db.commit()


async def boost_listing(listing_id: int, days: int) -> None:
    db = _db()
    await db.execute(
        """UPDATE listings
           SET boosted_until = datetime('now', ?), updated_at = datetime('now')
           WHERE id = ?""",
        (f"+{days} days", listing_id),
    )
    await db.commit()


async def search_listings(
    deal: str | None = None,
    ptype: str | None = None,
    district: str | None = None,
    rooms: int | None = None,
    price_max: int | None = None,
    limit: int = 10,
    offset: int = 0,
):
    q = "SELECT * FROM listings WHERE status = 'active'"
    args: list[Any] = []
    if deal:
        q += " AND deal = ?"
        args.append(deal)
    if ptype:
        q += " AND ptype = ?"
        args.append(ptype)
    if district:
        q += " AND district = ?"
        args.append(district)
    if rooms:
        q += " AND rooms = ?"
        args.append(rooms)
    if price_max:
        q += " AND price <= ?"
        args.append(price_max)
    q += " ORDER BY (boosted_until IS NOT NULL AND boosted_until > datetime('now')) DESC, created_at DESC LIMIT ? OFFSET ?"
    args.extend([limit, offset])
    cur = await _db().execute(q, args)
    return await cur.fetchall()


async def count_search_listings(
    deal: str | None = None,
    ptype: str | None = None,
    district: str | None = None,
    rooms: int | None = None,
    price_max: int | None = None,
) -> int:
    q = "SELECT COUNT(*) c FROM listings WHERE status = 'active'"
    args: list[Any] = []
    if deal:
        q += " AND deal = ?"
        args.append(deal)
    if ptype:
        q += " AND ptype = ?"
        args.append(ptype)
    if district:
        q += " AND district = ?"
        args.append(district)
    if rooms:
        q += " AND rooms = ?"
        args.append(rooms)
    if price_max:
        q += " AND price <= ?"
        args.append(price_max)
    cur = await _db().execute(q, args)
    row = await cur.fetchone()
    return row["c"] if row else 0


async def get_user_listings(user_id: int):
    cur = await _db().execute(
        "SELECT * FROM listings WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    )
    return await cur.fetchall()


async def listings_to_nudge(after_days: int, cooldown_days: int, limit: int = 20):
    """Active listings that are currently NOT boosted and were not nudged recently.

    This is the revenue loop: the owner gets a reminder that Boost makes the
    listing first in search. Cooldown keeps the reminder from becoming spam.
    """
    q = """SELECT * FROM listings
           WHERE status = 'active'
             AND (boosted_until IS NULL OR boosted_until <= datetime('now'))
             AND created_at <= datetime('now', ?)
             AND (nudged_at IS NULL OR nudged_at <= datetime('now', ?))
           ORDER BY created_at LIMIT ?"""
    cur = await _db().execute(q, (f"-{after_days} days", f"-{cooldown_days} days", limit))
    return await cur.fetchall()


async def mark_nudged(listing_id: int) -> None:
    db = _db()
    await db.execute("UPDATE listings SET nudged_at = datetime('now') WHERE id = ?", (listing_id,))
    await db.commit()


async def all_user_tg_ids():
    cur = await _db().execute("SELECT tg_id FROM users ORDER BY id")
    return [r["tg_id"] for r in await cur.fetchall()]


async def log_boost(listing_id: int, user_id: int, stars: int, days: int, status: str = "paid") -> int:
    db = _db()
    cur = await db.execute(
        "INSERT INTO boosts (listing_id, user_id, stars, days, status) VALUES (?, ?, ?, ?, ?)",
        (listing_id, user_id, stars, days, status),
    )
    await db.commit()
    return cur.lastrowid


async def log_payment(user_id: int, listing_id: int | None, purpose: str, stars: int,
                      currency: str, telegram_charge_id: str, provider_charge_id: str | None) -> None:
    db = _db()
    await db.execute(
        """INSERT INTO payments
           (user_id, listing_id, purpose, stars, currency, telegram_charge_id, provider_charge_id)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user_id, listing_id, purpose, stars, currency, telegram_charge_id, provider_charge_id),
    )
    await db.commit()


async def log_event(name: str, user_id: int | None = None, listing_id: int | None = None, meta: str | None = None) -> None:
    db = _db()
    await db.execute(
        "INSERT INTO events (name, user_id, listing_id, meta) VALUES (?, ?, ?, ?)",
        (name, user_id, listing_id, meta),
    )
    await db.commit()


async def stats() -> dict:
    db = _db()
    out: dict[str, Any] = {}
    for name, q in {
        "users": "SELECT COUNT(*) c FROM users",
        "listings": "SELECT COUNT(*) c FROM listings",
        "active": "SELECT COUNT(*) c FROM listings WHERE status='active'",
        "pending": "SELECT COUNT(*) c FROM listings WHERE status='pending'",
        "boosts": "SELECT COUNT(*) c FROM boosts WHERE status='paid'",
        "payments": "SELECT COUNT(*) c FROM payments",
        "revenue_stars": "SELECT COALESCE(SUM(stars),0) c FROM payments",
    }.items():
        cur = await db.execute(q)
        row = await cur.fetchone()
        out[name] = row["c"]
    return out
