#!/usr/bin/env bash
# Install the daily DB backup that RUNBOOK §12 promised but never shipped.
#
#   scp deploy/apply_backup.sh root@<IP>:/tmp/
#   ssh root@<IP> "sed -i 's/\r$//' /tmp/apply_backup.sh && bash /tmp/apply_backup.sh"
#
# Idempotent: safe to run again. Writes /opt/imobiliare/backup.py, a cron entry, runs one backup
# immediately and proves the archive is readable (integrity_check) — a backup nobody verified is
# not a backup. Money tables are the only irreducible data in this project: listings can be
# re-submitted, payments cannot be re-created.
set -e

DB=/opt/imobiliare/data/imobiliare.db
DIR=/opt/imobiliare/data/backups
PY=/opt/imobiliare/venv/bin/python

mkdir -p "$DIR"

cat > /opt/imobiliare/backup.py <<'PYEOF'
"""Consistent SQLite + .env backup with rotation. Called by cron, safe to call by hand."""
import os
import sqlite3
import subprocess
import sys
import time

DB = "/opt/imobiliare/data/imobiliare.db"
ENV = "/opt/imobiliare/bot/.env"
OUT = "/opt/imobiliare/data/backups"
KEEP_DAYS = 14


def snapshot():
    dst = os.path.join(OUT, "imobiliare-%s.db" % time.strftime("%Y%m%d-%H%M%S"))
    src = sqlite3.connect(DB)
    dstcon = sqlite3.connect(dst)
    with dstcon:
        src.backup(dstcon)          # WAL-safe, unlike copying the .db file
    src.close()
    dstcon.close()
    os.chmod(dst, 0o600)
    return dst


def main():
    os.makedirs(OUT, exist_ok=True)
    dst = snapshot()
    con = sqlite3.connect(dst)
    ok = con.execute("pragma integrity_check").fetchone()[0]
    n_list = con.execute("select count(*) from listings").fetchone()[0]
    n_pay = con.execute("select count(*) from payments").fetchone()[0]
    n_card = con.execute("select count(*) from card_orders").fetchone()[0]
    con.close()
    if ok != "ok":
        print("БЭКАП ПОВРЕЖДЁН: integrity_check =", ok, dst)
        return 1
    print("backup:", dst, os.path.getsize(dst), "bytes | integrity ok |",
          "listings", n_list, "payments", n_pay, "card_orders", n_card)

    # .env holds BOT_TOKEN and the LS signing secret: without it a restore means a new bot and a
    # re-registered webhook. Owner-readable only.
    if os.path.exists(ENV):
        envdst = dst + ".env"
        subprocess.run(["cp", ENV, envdst], check=True)
        os.chmod(envdst, 0o600)
        print("env snapshot:", envdst)

    # Photos: one rolling tar, re-downloadable from Telegram by file_id, so we keep just the latest.
    photos = os.path.join(os.path.dirname(DB), "photos")
    if os.path.isdir(photos) and os.listdir(photos):
        tgz = os.path.join(OUT, "photos-latest.tgz")
        subprocess.run("tar czf %s -C %s photos" % (tgz, os.path.dirname(DB)),
                       shell=True, check=True)
        print("photos:", tgz, os.path.getsize(tgz), "bytes,", len(os.listdir(photos)), "files")

    # rotation: db snapshots (and their .env twins) older than KEEP_DAYS
    cutoff = time.time() - KEEP_DAYS * 86400
    removed = 0
    for name in sorted(os.listdir(OUT)):
        p = os.path.join(OUT, name)
        if name.startswith("imobiliare-") and os.path.getmtime(p) < cutoff:
            os.remove(p)
            if os.path.exists(p + ".env"):
                os.remove(p + ".env")
            removed += 1
    print("rotated:", removed, "файл(ов) старше", KEEP_DAYS, "дней")
    return 0


if __name__ == "__main__":
    sys.exit(main())
PYEOF

cat > /etc/cron.d/imobiliare-backup <<EOF
# daily money backup, 03:00 (see RUNBOOK §12)
0 3 * * * root $PY /opt/imobiliare/backup.py >> /var/log/imobiliare-backup.log 2>&1
EOF
chmod 644 /etc/cron.d/imobiliare-backup

echo "=== cron ==="
systemctl is-active cron 2>/dev/null || service cron status 2>/dev/null || echo "cron NOT running — check me"

echo "=== first backup right now ==="
$PY /opt/imobiliare/backup.py

echo "=== contents ==="
ls -la "$DIR" | tail -5
echo "=== restore (RUNBOOK 16) ==="
LAST=$(ls -1 "$DIR"/imobiliare-*.db 2>/dev/null | tail -1)
echo "systemctl stop imobiliare imobiliare-web"
echo "cp $LAST $DB"
echo "cp $LAST.env /opt/imobiliare/bot/.env    # если снапшот .env есть"
echo "systemctl start imobiliare imobiliare-web && bash /tmp/status.sh"
echo "OK: backup стоит, первый файл проверен integrity_check"
