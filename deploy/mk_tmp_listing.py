import sqlite3
db = sqlite3.connect("/opt/imobiliare/data/imobiliare.db")
cur = db.execute(
    "INSERT INTO listings (user_id,deal,ptype,price,currency,district,status,photos,phone,description) "
    "VALUES (1,'rent','apartment',450,'EUR','Centru Test','active','[]','+37112345678','тестовое объявление для проверки API')"
)
db.commit()
print("TEMP_ID", cur.lastrowid)
