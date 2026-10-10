"""Read-only audit of production DB. Run on server: /opt/imobiliare/venv/bin/python audit.py"""
import sqlite3

c = sqlite3.connect("file:/opt/imobiliare/data/imobiliare.db?mode=ro", uri=True)
q = lambda s: c.execute(s).fetchall()

print("users:", q("select count(*) from users")[0][0])
print("listings by status:", q("select status, count(*) from listings group by status"))
print("with photos:", q("select count(*) from listings where photos != '[]'")[0][0])
print("real (non-seed) listings:", q("select count(*) from listings where id not in (select id from listings where description like '%seed%')")[0][0])
print("sample listings:", q("select id, deal, ptype, price, district, status, views from listings order by id limit 10"))
print("boosts:", q("select count(*) from boosts")[0][0], q("select * from boosts limit 5"))
print("payments:", q("select count(*) from payments")[0][0], q("select * from payments limit 5"))
print("events:", q("select name, count(*) from events group by name order by 2 desc"))
print("last events:", q("select name, user_id, created_at from events order by id desc limit 10"))
