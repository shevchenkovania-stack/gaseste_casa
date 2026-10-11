"""Smoke-test the share/referral loop against the REAL prod .env (BOT_USERNAME etc).

No money, no writes: it only checks the link the marketing machine puts in front of a user is
well-formed and round-trips back to a `share_<id>` deep link. Run:
  cd /opt/imobiliare/bot && /opt/imobiliare/venv/bin/python /tmp/test_share.py
"""
import urllib.parse as p

import config
import keyboards

print("BOT_URL:", config.BOT_URL or "(empty - share buttons hidden)")
assert config.BOT_URL, "BOT_USERNAME must be set for the share loop to work"

# per-listing share link must decode back to ?start=share_<id>
u = keyboards.share_url(7)
q = p.parse_qs(p.urlparse(u).query)
assert q["url"][0] == f"{config.BOT_URL}?start=share_7", q["url"]
assert "Găsește" in q["text"][0], q["text"]
print("listing share deep:", q["url"][0])

# product-level share link (menu / channel) points at the bot itself
g = p.parse_qs(p.urlparse(keyboards.share_url()).query)
assert g["url"][0] == config.BOT_URL, g["url"]
print("product share deep:", g["url"][0])

# the buttons are actually rendered where users will see them
listing_rows = [[b.text for b in r] for r in keyboards.listing_kb(7, True, False).inline_keyboard]
assert any("Поделиться" in t for r in listing_rows for t in r), listing_rows
menu_rows = [[b.text for b in r] for r in keyboards.main_menu().inline_keyboard]
assert any("Позвать" in t for r in menu_rows for t in r), menu_rows
print("buttons: listing + menu OK")

print("✅ SHARE LOOP OK")
