#!/usr/bin/env bash
# Remove DEMO/test residue so nothing fake is visible to a real user.
# Scoped strictly to the rows the test tooling creates: a ДЕМО card and everything that points at it
# (events / boosts / payments / card_orders). A real listing never contains the substring "ДЕМО",
# so this cannot touch genuine objects. Idempotent - safe to re-run.
set -e
/opt/imobiliare/venv/bin/python - <<'PYEOF'
import sqlite3
d = sqlite3.connect('/opt/imobiliare/data/imobiliare.db')
d.row_factory = sqlite3.Row
demo_ids = [r["id"] for r in d.execute("SELECT id FROM listings WHERE description LIKE '%ДЕМО%'")]
print("ДЕМО listings to drop:", demo_ids)
for lid in demo_ids:
    for table in ("events", "boosts", "payments", "card_orders", "listings"):
        d.execute(f"DELETE FROM {table} WHERE listing_id = ?" if table != "listings"
                  else "DELETE FROM listings WHERE id = ?", (lid,))
d.commit()
print("counts after: listings",
      d.execute("SELECT COUNT(*) c FROM listings").fetchone()["c"],
      "| boosts", d.execute("SELECT COUNT(*) c FROM boosts").fetchone()["c"],
      "| payments", d.execute("SELECT COUNT(*) c FROM payments").fetchone()["c"],
      "| card_orders", d.execute("SELECT COUNT(*) c FROM card_orders").fetchone()["c"])
print("remaining listings:",
      [tuple(r) for r in d.execute("SELECT id,status,district,price,currency FROM listings")])
PYEOF
