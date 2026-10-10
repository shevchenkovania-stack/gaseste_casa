# RUNBOOK — полное описание проекта «Găsește Casa / ChirieBot»

**Зачем этот файл:** чтобы проект можно было восстановить с нуля **только по нему** — на новом сервере,
после потери кода, после смерти ноутбука, или через полгода, когда всё забылось.
Секретов здесь нет: токены, пароли и IP — в `ACCESS.md` (не в git).

Связанные документы: `MISSION.md` (правила и автономность агента), `STATUS.md` (снятие состояния
«что работает / что нет» на сегодня), `GROWTH.md` (наполнение доски, тексты, цены, платёжные рельсы).

---

## 1. Что это за продукт

Маркетплейс аренды и продажи недвижимости Кишинёва **внутри Telegram**:

- **Telegram-бот** (`@gaseste_casa_bot`) — поиск с фильтрами, подача объявления (бесплатно),
  модерация, «мои объявления», платный **Boost**.
- **Публичный канал** `t.me/gaseste_casa` — бот сам постит каждое одобренное объявление с фото,
  контактом владельца и CTA «разместить своё». Это витрина и источник новых подач.
- **Mini App** (aiohttp + один SPA) — веб-витрина с фильтрами; работает, но пока не опубликована
  (нет домена/HTTPS).
- **Платный продукт один:** Boost = объявление поднимается на первое место в поиске и
  выделяется ⭐ на `BOOST_DAYS` дней. Цена: `BOOST_MDL` MDL переводом на карту (основной путь)
  или `BOOST_STARS` Telegram Stars ⭐.

Метрика успеха (см. MISSION.md §18): **`REAL_REVENUE > 0`** — первый реальный платёж от клиента.
Считается по таблице `payments`: сумма `stars` при `currency='XTR'` и сумма `amount` при `currency='MDL'`;
тестовые `XTEST` в выручку не попадают.

---

## 2. Карта репозитория

```
bot/                     код бота и Mini App (один venv, один репозиторий)
  main.py                точка входа: Bot/Dispatcher, подключение роутеров, запуск scheduler
  config.py              все настройки из ENV (единственный источник конфигурации)
  constants.py           подписи deal/ptype/status, список районов Кишинёва, ROOMS
  db.py                  схема SQLite + все SQL-запросы (единственный слой доступа к данным)
  keyboards.py           все inline-клавиатуры (единственное место, где живут callback_data)
  render.py              текстовые карточки объявлений (caption, кнопки списков)
  publish.py             выкладка одобренного объявления: скачивание фото + пост в канал
  scheduler.py           фоновые задачи; единственная важная — Boost-нудж (двигатель выручки)
  requirements.txt       aiogram, aiosqlite, aiohttp, python-dotenv
  .env.example           шаблон ENV-файла (реальный .env в git не попадает)
  handlers/
    start.py             /start, /menu, deep links (?start=метка, /startapp boost:<id>), /paysupport
    add.py               FSM подачи объявления (11 состояний) + уведомление админов
    browse.py            FSM поиска (deal → ptype → district → результаты с пагинацией)
    profile.py           «Мои объявления»
    boost.py             оба платёжных рельса: Stars-инвойс и ручной перевод MDL
    admin.py             модерация, подтверждение ручных платежей, /stats /pending /nudge /broadcast
  webapp/
    app.py               aiohttp-сервер: /api/listings, /api/listing/{id}, POST .../contact, /api/stats, /photos/
    static/index.html    SPA-витрина (фильтры, карточка, «связаться», Boost для владельца)
deploy/                  всё, что связано с сервером и проверками (ничего не импортируется ботом)
  imobiliare.service     systemd unit бота
  imobiliare-web.service systemd unit Mini App
  nginx-chirie.conf      шаблон reverse-proxy (ждёт домен)
  apply_nudge.sh, apply_manual.sh, verify_nudge.sh, verify_manual.sh, status.sh,
  cleanup_test.sh, test_money_path.py, make_demo.py, post_promo.py, audit.py, whoami.sh,
  seed.py, mk_tmp_listing.py, setup_channel.py, set_avatar*, make_avatar.py, test_render.py,
  test_publish.py, test_webapp.sh, apply_webapp.sh, fix_test.sh
MISSION.md / STATUS.md / GROWTH.md / RUNBOOK.md
ACCESS.md                (в .gitignore) SSH, пароли, IP, id бота/канала
```

Стек: **Python 3.12, aiogram 3 (polling, не webhook), aiosqlite, aiohttp, SQLite (WAL), systemd, Ubuntu 24.04.**
Никаких фреймворков, ORM, Docker, celery, redis — осознанно (см. §14 «Решения»).

---

## 3. Архитектура и потоки данных

```
Telegram-пользователь ──> aiogram polling ──> handlers/* ──> db.py (aiosqlite, WAL) ──> /opt/imobiliare/data/imobiliare.db
                                  │                                   ▲
                                  ├──> publish.py ──> канал @gaseste_casa (posts + фото)
                                  │                                   │
scheduler.py (тот же процесс) ────┘              webapp/app.py (aiohttp, 127.0.0.1:8085)
                                                    ▲  читает ту же БД, пишет views/contacts
                                                    │
                                                SPA index.html (пока только локально)
```

Три важных факта:

1. **Одна SQLite на два процесса.** Поэтому `PRAGMA journal_mode=WAL` и `busy_timeout=5000`
   обязательны — без них бывают `database is locked`.
2. **Бот на polling, не на webhook.** Никаких открытых портов наружу: снаружи только SSH :22 (`ufw` это держит).
3. **Порядок роутеров в `main.py` имеет значение:** `start, add, browse, profile, boost, admin`.
   `boost.router` должен быть раньше `admin.router`, потому что админ обрабатывает `manapp:`/`manrej:`,
   а буст — `manual:`/`manualpaid:` (префикс `man` общий). Обработчики выбраны так, чтобы не коллизировать.

---

## 4. Конфигурация (ENV)

Единственный источник — `/opt/imobiliare/bot/.env` (права root:600), читается `python-dotenv`.
Ключей и значений по умолчанию:

| Ключ | По умолчанию | Зачем | Текущее прод-значение |
|---|---|---|---|
| `BOT_TOKEN` | пусто (бот не стартует) | токен от @BotFather | секрет → `ACCESS.md` |
| `ADMIN_IDS` | пусто | через запятую tg id; доступ к модерации и `/stats` | `1182157446` |
| `DB_PATH` | `/opt/imobiliare/data/imobiliare.db` | файл SQLite | по умолчанию |
| `PHOTOS_DIR` | `/opt/imobiliare/data/photos` | jpg для Mini App, имена `{listing_id}_{i}.jpg` | по умолчанию |
| `DEFAULT_CURRENCY` | `EUR` | валюта prices в боте | `EUR` |
| `BOOST_STARS` | `50` | цена Boost в Telegram Stars | `50` |
| `BOOST_DAYS` | `7` | на сколько дней Boost | `7` |
| `BOOST_MDL` | `0` (опция скрыта) | цена Boost в MDL переводом; **0 выключает рельс** | `100` |
| `PAY_INFO` | пусто | реквизиты, которые видит покупатель | **пусто — надо заполнить** |
| `NUDGE_AFTER_DAYS` | `2` | через сколько дней после подачи напоминать про Boost | `2` |
| `NUDGE_COOLDOWN_DAYS` | `4` | как часто можно напоминать по одному объявлению | `4` |
| `NUDGE_INTERVAL_HOURS` | `6` | период проверки (цикл sleeping **первым**, значит первый проход через 6 ч после рестарта) | `6` |
| `CONTACT_URL` | пусто | контакт поддержки в `/paysupport` | пусто |
| `CHANNEL_ID` | пусто → публикация в канал выключена | `@username` публичного канала или `-100...` id | `@gaseste_casa` |
| `CHANNEL_URL` | *(вычисляется)* | `https://t.me/<username>` если `CHANNEL_ID` начинается с `@` | t.me/gaseste_casa |
| `BOT_USERNAME` | пусто | для CTA-кнопок в постах канала | `gaseste_casa_bot` |
| `BOT_URL` | *(вычисляется)* | `https://t.me/<BOT_USERNAME>` | — |
| `WEBAPP_URL` | пусто → кнопка «Открыть приложение» скрыта | публичный HTTPS адрес Mini App | **пусто (нет домена)** |
| `STARS_CURRENCY` | `XTR` (константа, не ENV) | валюта Stars-инвойсов | `XTR` |

Правило: **любая новая настройка = ключ в `config.py` + строка в `.env.example` + строка в эту таблицу.**
Никаких значений, зашитых в обработчиках.

---

## 5. База данных

Схема создаётся автоматически при старте бота (`db.init_db()` → `executescript(SCHEMA)`),
дополнительные колонки — миграцией `_migrate()` в том же месте. Мини-ап БД руками для первичного создания не нужен.

```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_id INTEGER UNIQUE NOT NULL, username TEXT, first_name TEXT, phone TEXT,
    is_admin INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    deal TEXT NOT NULL,            -- rent | sale
    ptype TEXT NOT NULL,           -- apartment | house | room
    rooms INTEGER, price INTEGER NOT NULL, currency TEXT DEFAULT 'EUR',
    district TEXT, area REAL, floor INTEGER, floors INTEGER,
    phone TEXT, description TEXT,
    photos TEXT DEFAULT '[]',      -- JSON-массив Telegram file_id (не пути!)
    status TEXT DEFAULT 'pending', -- pending | active | rejected | archived
    boosted_until TEXT,            -- datetime('now','+N days') — признак живого Boost
    nudged_at TEXT,                -- добавлено миграцией: когда последний раз напоминали про Boost
    created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now')),
    views INTEGER DEFAULT 0
);
CREATE TABLE boosts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER NOT NULL REFERENCES listings(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    stars INTEGER NOT NULL,        -- цена в Stars; для ручных заявок туда пишется сумма в MDL
    days INTEGER NOT NULL,
    status TEXT DEFAULT 'pending', -- pending | paid | manual_pending | manual | manual_rejected
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL, listing_id INTEGER,
    purpose TEXT,                  -- boost | boost_test | boost_manual
    stars INTEGER,                 -- сумма в Stars (0 для MDL)
    currency TEXT,                 -- XTR | XTEST | MDL
    telegram_charge_id TEXT, provider_charge_id TEXT,
    amount REAL,                   -- добавлено миграцией: реальная сумма в MDL
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL, user_id INTEGER, listing_id INTEGER, meta TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX idx_listings_status ON listings(status);
CREATE INDEX idx_listings_district ON listings(district);
```

Ключевые запросы (все живут в `db.py`, менять только там):

- выдача поиска: `WHERE status='active'` +
  `ORDER BY (boosted_until IS NOT NULL AND boosted_until > datetime('now')) DESC, created_at DESC` —
  то есть Boost — это **не отдельная таблица, а колонка-просрочка**;
- `listings_to_nudge(after_days, cooldown_days, limit=20)` — активные, не в бусте, старше N дней,
  не nudged recently;
- `stats()` — пользователи, объявления, `boosts WHERE status IN ('paid','manual')`,
  `revenue_stars` (только `currency='XTR'`), `revenue_mdl` (сумма `amount`, `currency='MDL'`),
  `test_payments` (`currency='XTEST'`).

Полезные ручные проверки (на сервере, `sqlite3` CLI не ставился — через venv-питон):

```bash
/opt/imobiliare/venv/bin/python -c "import sqlite3;d=sqlite3.connect('/opt/imobiliare/data/imobiliare.db');\
print(d.execute('select count(*) from listings').fetchone(), d.execute(\"select status,count(*) from listings group by status\").fetchall(),\
d.execute('select sum(amount) from payments where currency=\"MDL\"').fetchone())"
```

---

## 6. Пространство имён callback_data и FSM

Полная таблица — чтобы не придумывать конфликтов при новых кнопках.

| Префикс | Обработчик | Несёт | Что делает |
|---|---|---|---|
| `menu:home/search/add/my/help` | start.py, browse.py, add.py, profile.py | — | главное меню и входы в сценарии |
| `cancel` | везде (fallback-кнопки) | — | отмена FSM |
| `deal:` `ptype:` `rooms:` `district:` `area:skip` `floor:skip` `desc:skip` `phone:skip` `add:photos_done` `add:photos_skip` `add:confirm` | add.py | id / `skip` | шаги подачи объявления |
| `fdeal:` `fptype:` `fdist:` `page:next` `page:prev` `noop` | browse.py | значение или `all` | фильтры поиска и пагинация |
| `view:` | browse.py | listing_id | карточка объявления (+inc_views, если не владелец) |
| `contact:` | browse.py | listing_id | показать телефон/юзернейм владельца |
| `boost:` | boost.py | listing_id | оффер Boost (оба рельса) |
| `boostpay:` | boost.py | listing_id | `send_invoice` в XTR |
| `manual:` | boost.py | listing_id | инструкция перевода MDL (`PAY_INFO`) |
| `manualpaid:` | boost.py | listing_id | заявка «я перевёл» → `boosts.status='manual_pending'` + уведомления админам |
| `mod:approve:` `mod:reject:` | admin.py | listing_id | модерация |
| `manapp:` `manrej:` | admin.py | boost_id | подтвердить / отклонить ручной платёж |
| `back:search` | browse.py | — | вернуться к результатам |

Состояния FSM: `AddListing = deal, ptype, rooms, district, price, area, floor, description, phone, photos, confirm`
(11 состояний; подписи в тексте — «Шаг 1/8…», это косметика). `Search = deal, ptype, district, results`.
Хранилище состояний — MemoryStorage (не сохраняется между рестартами: недоподанное объявление просто теряется,
это осознанно принято как приемлемое).

---

## 7. Пользовательские сценарии (как выглядит изнутри)

**Подача объявления:** `/start` → «➕ Разместить объект» → 8 шагов вопросов (тип сделки, тип объекта,
комнаты, район из `constants.DISTRICTS`, цена числом, площадь/этаж — можно «Пропустить», описание,
телефон) → 1–10 фото (берётся `message.photo[-1].file_id`) → сводка «✅ Опубликовать» → `db.create_listing(status='pending')`
→ `events.listing_created` → всем админам карточка с кнопками «Одобрить/Отклонить».

**Модерация:** `mod:approve` → `status='active'` → владельцу «одобрено» + **`publish.publish_listing`**
(скачать фото в `PHOTOS_DIR` как `{id}_{i}.jpg`, затем в канал: `send_media_group` с caption
+ отдельное сообщение с кнопками «Написать владельцу / Смотреть все объекты / ➕ Разместить своё»),
`events.channel_post` c id сообщений в `meta`. Публикация обёрнута в `try/except` — сбой канала
**никогда не должен** блокировать модерацию. `mod:reject` → статус + уведомление владельцу.

**Поиск:** «🔍 Поиск» → сделка → тип → район → список кнопками (текст из `render.listing_button_text`,
⭐ в начале если бустнутый) по 10 на страницу → карточка.

**Boost из бота:** карточка своего объявления → «🚀 Поднять (Boost)» → оффер. Чужое объявление — «Поднять можно только своё».

**Deep links:**
- `t.me/gaseste_casa_bot?start=<метка>` — метка пишется в `events.start.meta` (реестр источников трафика),
  используется во всех рассылках/постах;
- `/startapp boost:<id>` — из Mini App (SPA зовёт `Telegram.WebApp.openTelegramLink`), сразу показывает оффер.

**Mini App API** (`webapp/app.py`, порт 127.0.0.1:8085):

| Метод/путь | Авторизация | Что делает |
|---|---|---|
| `GET /` | — | отдаёт `static/index.html` |
| `GET /api/listings?deal=&ptype=&district=&rooms=&price_max=&page=` | — | активные, буст сначала, 20/страница |
| `GET /api/listing/{id}` | initData в заголовке `X-Init-Data` (опционально) | детали; `views+1`; `events.web_view` |
| `POST /api/listing/{id}/contact` | **обязательна** initData | телефон/ tg владельца; `events.web_contact` (401 без авторизации) |
| `GET /api/stats` | — | `{"active": N}` |
| `GET /photos/{file}` | — | статика из `PHOTOS_DIR` |

Валидация initData — детерминированная по документации Telegram: `secret = HMAC_SHA256(key="WebAppData", msg=BOT_TOKEN)`,
`hash = HMAC_SHA256(key=secret, msg=отсортированные "k=v\n" без hash)`, `auth_date` не старше 24 ч.
Сломанная подпись → `None` (для `/contact` это 401).

---

## 8. Деньги: два рельса + чем они ломаются

### Рельс 1 (основной) — перевод MDL с ручным подтверждением

Работает без эквайринга, без карты в Telegram, без ÎI на старте. Кнопка «💸 Переводом N MDL» стоит **выше** звёздной.

```
boost_kb → manual:<id> → сообщение с PAY_INFO и номером объявления
        → manualpaid:<id> → boosts(status='manual_pending', stars=BOOST_MDL, days=BOOST_DAYS)
        → каждому админу: «Ожидает подтверждения» + кнопки manapp:<boost_id> / manrej:<boost_id>
        → manapp → boosts.status='manual', boost_listing(days),
                   payments(purpose='boost_manual', currency='MDL', amount=BOOST_MDL,
                            telegram_charge_id='manual:<boost_id>'),
                   events.boost_manual_paid, владельцу «платёж получен, топ на N дней»
        → manrej  → boosts.status='manual_rejected', владельцу «не нашли деньги, попробуй ещё раз»
```

Защита от дублей: `find_boost(listing_id, 'manual_pending')` — вторая заявка по тому же объявлению
не создаёт записи, покупатель видит «Твой платёж уже на проверке».
Хранение цены: для ручных заявок `boosts.stars` = договорная сумма в **MDL** (комментарий в коде есть);
в `payments` это разведено: `stars=0, amount=<MDL>`.
Если `PAY_INFO` пустой, покупатель видит «реквизиты пришлёт модератор» — это **не** рабочий путь,
так и надо держать заполненным.

### Рельс 2 — Telegram Stars

`boostpay:<id>` → `send_invoice(currency='XTR', provider_token='', prices=[LabeledPrice('Boost', BOOST_STARS)],
payload='boost:<id>')` → `pre_checkout_query` (всегда `ok=True`) → `message.successful_payment` →
`boost_listing` + `boosts(status='paid')` + `payments(purpose='boost'|'boost_test', currency=sp.currency,
stars=total_amount, telegram_charge_id=…)` + `events.boost_paid` (или `test_paid`) + отчёт админам.

### Что известно про ошибки Telegram (проверено на проде 10.10)

| Сообщение | Когда | Что значит |
|---|---|---|
| `PROVIDER_ACCOUNT_INVALID` | пользователь пытается **купить** звёзды | к аккаунту Telegram не привязана карта. Не баг бота |
| «этот метод оплаты невалиден для этого типа товара» | на экране оплаты Stars-инвойса при 0 звёзд | Telegram пытается докупить звёзды и отказывает. `send_invoice` при этом успешен (в логах чисто) — вина не кода |
| `PAYMENT_PROVIDER_INVALID` | бот шлёт тестовый XTEST-инвойс | продакшн-ботам тестовые платежи **запрещены**; XTEST работает только ботам в test-окружении. Обработчик `XTEST` в коде оставлен на будущее |

**Вывод, который надо помнить:** проверить кассу «бесплатно» нельзя ни одним способом.
Единственный бесплатный прогон — рельс MDL (см. §11 «тест без денег»).

---

## 9. Двигатель выручки (`scheduler.py`)

В том же процессе, что и бот: `asyncio.create_task(scheduler.run(bot))` рядом с `dp.start_polling`,
`job.cancel()` в `finally`. Цикл **спит первым** (`NUDGE_INTERVAL_HOURS*3600`), поэтому после рестарта
проход не наваливается сразу. Любое исключение внутри прохода ловится и **не убивает** цикл
(`except asyncio.CancelledError: raise` выше общего `except` — иначе задача не осталась бы отменяемой).

`nudge_unboosted(bot)`: для каждой строки из `listings_to_nudge` → владельцу ЛС с текстом
(объявление, район, цена, просмотры) и `boost_kb` (обе кнопки); `mark_nudged(listing_id)`;
`events.boost_nudge`. Если ЛС недоступны (пользователь заблокировал бота) — запись всё равно
помечается, чтобы не долбить каждый проход. Вручную тот же проход: `/nudge`.

---

## 10. Развёртывание с нуля (чистый Ubuntu 24.04, один прогон)

Ниже — полный путь от «сервера нет» до живого бота. Все команды от root.

```bash
# 1. пакеты и структура
apt update && apt install -y python3.12-venv unzip curl
mkdir -p /opt/imobiliare/data/photos
# 2. venv + зависимости
python3 -m venv /opt/imobiliare/venv
/opt/imobiliare/venv/bin/pip install --upgrade pip
/opt/imobiliare/venv/bin/pip install aiogram aiosqlite aiohttp python-dotenv
# (или: pip install -r bot/requirements.txt после копирования кода)
# 3. код (см. §11: копированием по scp; на сервере git не настроен)
#    /opt/imobiliare/bot/{config.py,constants.py,db.py,keyboards.py,render.py,publish.py,
#                         scheduler.py,main.py,requirements.txt,handlers/*.py,webapp/app.py,webapp/static/index.html}
# 4. .env — ключи и значения бери из таблицы §4, токен из @BotFather
cat > /opt/imobiliare/bot/.env <<'EOF'
BOT_TOKEN=<токен от BotFather>
ADMIN_IDS=1182157446
DB_PATH=/opt/imobiliare/data/imobiliare.db
PHOTOS_DIR=/opt/imobiliare/data/photos
DEFAULT_CURRENCY=EUR
BOOST_STARS=50
BOOST_DAYS=7
BOOST_MDL=100
PAY_INFO=<карта/IBAN, банк, получатель>
NUDGE_AFTER_DAYS=2
NUDGE_COOLDOWN_DAYS=4
NUDGE_INTERVAL_HOURS=6
CHANNEL_ID=@gaseste_casa
BOT_USERNAME=gaseste_casa_bot
WEBAPP_URL=
EOF
chmod 600 /opt/imobiliare/bot/.env
# 5. systemd (файлы лежат в deploy/)
cp deploy/imobiliare.service deploy/imobiliare-web.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now imobiliare imobiliare-web
# 6. проверка
systemctl is-active imobiliare imobiliare-web
journalctl -u imobiliare -n 20 --no-pager -o cat
curl -s http://127.0.0.1:8085/api/stats      # -> {"active":N}
bash /tmp/status.sh                            # см. §11
```

**Первичная настройка в Telegram (это делает человек, бот не может):**

1. @BotFather: `newbot` (или взять существующего `@gaseste_casa_bot`), имя «Găsește Casa | Аренда Кишинёв»,
   короткое имя; токен → `.env`.
2. Создать **публичный канал** `t.me/gaseste_casa`, добавить бота **админом** с правом публикации,
   в `.env` `CHANNEL_ID=@gaseste_casa`, `BOT_USERNAME=gaseste_casa_bot`, рестарт.
   (Если канал приватный — нужен id вида `-100…`.)
3. Админ должен нажать `/start` в боте, иначе у него нет строки в `users` и демо-объявление создать нечем.
4. Пост-визитка в канал и её закрепление: `deploy/post_promo.py` (на проде это message_id **4**).

**Mini App наружу (не сделано):** домен → A-запись на VPS → `apt install nginx certbot python3-certbot-nginx`
→ `deploy/nginx-chirie.conf` (заменить `imobil.REPLACE_ME.md`) в `/etc/nginx/sites-available/`,
`ln -s`, `nginx -t`, `certbot --nginx -d <домен>` → `WEBAPP_URL=https://<домен>` в `.env` → рестарт бота
(появится кнопка «Открыть приложение») → в @BotFather: `/newapp` (или Bot Settings → Menu Button) на этот URL.
`ufw` при этом должен открыть 80/443: `ufw allow 'Nginx Full'`.

Безопасность (теперь нарушено, чинить при случае): оба сервиса идут от `root`; нужен отдельный
`User=`; бэкапы БД отсутствуют; пароль VPS менялся (см. `ACCESS.md`), SSH-ключ не добавлен;
`imobiliare-web` слушает только 127.0.0.1 и наружу не смотрит.

---

## 11. Деплой изменений и проверка (рабочая рутина)

Код на сервере = копия локального (git на сервере нет). Один цикл:

```powershell
# из c:\WORK\Projects\onedollorproject (PowerShell: && НЕ работает, разделитель ;)
scp bot/config.py bot/db.py root@<IP>:/opt/imobiliare/bot/
scp bot/handlers/boost.py root@<IP>:/opt/imobiliare/bot/handlers/
scp deploy/verify_manual.sh root@<IP>:/tmp/
ssh root@<IP> "sed -i 's/\r$//' /tmp/verify_manual.sh && bash /tmp/verify_manual.sh"
```

```bash
# обязательная проверка компиляции перед рестартом (делает apply_manual.sh)
cd /opt/imobiliare/bot && /opt/imobiliare/venv/bin/python -m py_compile \
  config.py constants.py db.py keyboards.py scheduler.py publish.py render.py main.py \
  handlers/*.py webapp/app.py
systemctl restart imobiliare imobiliare-web && sleep 4
systemctl is-active imobiliare imobiliare-web && curl -s http://127.0.0.1:8085/api/stats
journalctl -u imobiliare -n 20 --no-pager -o cat
journalctl -u imobiliare-web -n 20 --no-pager   # TypeError здесь = битый app.py, откатывать надо оба сервиса
```

**Полный синк (когда локальный код и прод разошлись и нужна гарантированная идентичность):** scp-ом
все runtime-файлы из §2 (`bot/*.py`, `bot/handlers/*.py`, `bot/webapp/app.py`, `bot/webapp/static/index.html`),
затем блок компиляции выше и рестарт **обоих** сервисов. `bot/.env` на сервере не трогается — он вне репозитория.
Размеры файлов должны совпадать с локальными (`ls -l` на сервере против `Get-ChildItem bot/*.py`) — это самая
дешёвая проверка, что scp не оборвался.

**Железное правило PowerShell:** никогда не всовывать питон/JS внутрь `ssh "... python -c '...'"` —
PowerShell ломает кавычки и `[`. Всегда: файл `.sh`/`.py` → scp → `sed -i 's/\r$//'` → `bash`/`python`.

Готовые скрипты: `deploy/status.sh` (сервисы + счётчики БД + ключи .env + webapp + лог),
`deploy/apply_manual.sh` / `verify_manual.sh` (рельс MDL: registry обработчиков, схема, статусы),
`deploy/apply_nudge.sh` / `verify_nudge.sh` (нудж), `deploy/cleanup_test.sh`.

Тесты и боевые прогоны (запускаются на сервере, самоочищаются):

- `deploy/test_money_path.py` — вызывает **боевой** `scheduler.nudge_unboosted`, админ получает ЛС
  с рабочей кнопкой; потом чистит `listings.nudged_at` и тестовые события;
- `deploy/make_demo.py` — удаляет старые ДЕМО-карточки, создаёт активную «ДЕМО» карточку на админе
  и шлёт админу настоящий Boost-оффер (обе кнопки). Не публикуется в канал;
- `deploy/post_promo.py [message_id]` — пост-визитка в канал + пин; с аргументом **редактирует**
  существующий пост вместо дубля.

**Тест платёжного рельса без денег (единственно возможный):** ДЕМО-карточка → «💸 Переводом 100 MDL»
→ «💸 Я перевёл 100 MDL» → админу приходит заявка → «✅ Деньги пришли» → Boost активен,
`/stats` показывает `REAL_REVENUE MDL: 100`. Это **не** реальные деньги; чтобы не врать себе в метрике,
снеси тестовые строки:

```bash
/opt/imobiliare/venv/bin/python - <<'PY'
import sqlite3; d=sqlite3.connect('/opt/imobiliare/data/imobiliare.db')
d.execute("delete from payments where purpose='boost_manual'"); d.execute("delete from boosts where status='manual'")
d.execute("update listings set boosted_until=NULL where description like '%ДЕМО%'"); d.commit()
print(d.execute("select count(*) from payments").fetchone())
PY
```

---

## 12. Эксплуатация, бэкап, откат

Логи: `journalctl -u imobiliare -f`, `journalctl -u imobiliare-web -f`.
При рестарте бот шлёт всем админам «✅ ChirieBot запущен и готов к работе» — это и есть health-check.

```bash
# ручной бэкап (консистентно под WAL)
sqlite3 /opt/imobiliare/data/imobiliare.db ".backup /opt/imobiliare/data/backup-$(date +%F).db"   # sqlite3 CLI НЕ установлен
# поэтому так:
/opt/imobiliare/venv/bin/python -c "import sqlite3;s=sqlite3.connect('/opt/imobiliare/data/imobiliare.db');\
d=sqlite3.connect('/opt/imobiliare/data/backup.db');s.backup(d);print('ok')"
# cron-бэкап с ротацией (строка в /etc/cron.d/imobiliare)
0 3 * * * root /opt/imobiliare/venv/bin/python -c "import sqlite3,time;s=sqlite3.connect('/opt/imobiliare/data/imobiliare.db');\
o='/opt/imobiliare/data/bak-%d.db'%time.time();d=sqlite3.connect(o);s.backup(d)" && find /opt/imobiliare/data -name 'bak-*.db' -mtime -14 -delete
```

Восстановление из бэкапа: остановить оба сервиса → положить файл на `DB_PATH` → проверить
`select count(*) from listings/payments` → запустить.
Фото — отдельный каталог, бэкапится `tar czf photos-$(date +%F).tgz -C /opt/imobiliare/data photos`
(без них карточки в канале останутся, Mini App потеряет картинки; `file_id` в БД позволяют докачать).

Откат кода: на сервере git нет — значит копируем нужную ревизию локально
(`git checkout <sha> -- bot/`) и scp-ом сверху, затем рестарт.
История коммитов и есть источник правды: `git log --oneline`.

---

## 13. Админ-команды бота (только для `ADMIN_IDS`)

| Команда | Действие |
|---|---|
| `/stats` | пользователи, объявления (активных/на модерации), Boost'ы, платежи (и число тестовых), `REAL_REVENUE Stars`, `REAL_REVENUE MDL` |
| `/pending` | до 20 карточек на модерации с кнопками одобрить/отклонить |
| `/nudge` | немедленно пройтись по двигателю выручки (сколько офферов отправлено) |
| `/broadcast <текст>` | рассылка всем пользователям кроме админов, пауза 0.05 с, `events.broadcast` с `ok/total` |
| `/admin` | список команд |
| `/paysupport` | контакт по возвратам (для всех) |
| кнопки `manapp:`/`manrej:` | подтвердить/отклонить ручной MDL-платёж |

---

## 14. Решения и границы (почему именно так, не ломай без причины)

- **SQLite вместо Postgres:** одна машина, параллельных писателей два, весь масштаб — десятки тысяч строк.
  Миграции — аддитивные `ALTER TABLE` в `_migrate()` при старте, без Alembic.
- **polling вместо webhook:** не нужен TLS/порт, `Restart=always` перекрывает всё.
- **Boost = колонка `boosted_until`**, а не строка-слот: истёк сам — выпал из топа, никакой очистки не нужно.
- **Фото в двух видах:** `file_id` в БД (для бота) и `{id}_{i}.jpg` в `PHOTOS_DIR` (для Mini App и поста в канал),
  потому что `file_id` нельзя отдать веб-странице.
- **Никакого скрейпинга 999.md/otakoy** (MISSION: ToS + чужие фото). Наполнение только руками/через бота;
  шаблоны текстов — в `GROWTH.md`.
- **AI только для неструктурированного** (описания, классификация фото). Деньги, БД, платежи, конечные
  автоматы —
  детерминированный код. Сейчас AI не используется вообще.
- **Рельс MDL с ручным подтверждением, а не «прикрутить crypto»:** решение принято после
  `PROVIDER_ACCOUNT_INVALID`/`PAYMENT_PROVIDER_INVALID` (см. §8) — иначе проект стоит без платежей.
  Юридическая оговорка: регулярные переводы физлицу = предпринимательская деятельность; после 5–20 продаж
  открывать **ÎI (ИП) / microapă** с патентом на услуги и уходить в эквайринг (maib E-commerce, bpay.md, Fastpay).
- **Бюджет этапа ≤ €100**, хостинг — уже оплаченный VPS (Time4VPS), домен пока не куплен.
- **Секретов в git нет** (`.gitignore` закрывает `.env`, `ACCESS.md`, `*.db`, фото). BOT_TOKEN когда-то
  попал в три deploy-скрипта и в историю — вырезан кодом **и** переписан историей
  (`git filter-branch` + `reflog expire` + `gc --prune=now`) **до** первого пуша; на всякий случай
  токен стоит отозвать через @BotFather.

---

## 15. Текущее состояние и чего не хватает (синхронно с STATUS.md)

Прод: VPS Ubuntu 24.04, `imobiliare` + `imobiliare-web` active, бот `@gaseste_casa_bot` (id 8763027850),
канал `t.me/gaseste_casa` подключён и автопостит, закрепление визитки (message_id 4),
демо-карточка пересоздана (последняя — #10), реальных объявлений **0**, платежей **0**, `REAL_REVENUE = 0`.

Не сделано, по приоритету:

1. `PAY_INFO` пустой — рельс MDL не отдаёт реквизиты покупателю (человеческий шаг).
2. 0 реальных объявлений на доске — главный блокер, не код (нужно 3–5, потом 50–100).
3. Нет домена/HTTPS → Mini App недоступна пользователям, кнопка в боте скрыта.
4. Нет бэкапов БД, сервисы от root, нет rate-limit на подачу объявлений.
5. Нет возвратов (только `/paysupport`), нет напоминаний об истёкшем Boost.
6. Нет реестра источников трафика (`events.start.meta` уже пишет метки — данные есть, отчёта нет).
7. Эквайринг MDL / нормальный учёт — требует ÎI/SRL (отдельный человеческий шаг).

---

## 16. «Всё пропало»: порядок восстановления по пунктам

1. Прислать/найти: доступ к VPS (`ACCESS.md`), аккаунт Telegram с правами админа канала и бота.
2. `git clone https://github.com/shevchenkovania-stack/gaseste_casa.git` (репозиторий приватный)
   или, если репозиторий потерян: код есть на сервере в `/opt/imobiliare/bot/` — забрать `scp -r`.
3. §10 шаги 1–2 (venv + requirements).
4. Если БД цела — просто скопировать `/opt/imobiliare/data/` и продолжить с шага 6.
   Если БД потеряна — создать пустую (сделается при старте), затем: `deploy/seed.py` для демо-наполнения,
   объявления владельцев придётся собирать заново.
5. `.env` по таблице §4; токен — из @BotFather (если потерян, `revoke` и новый), `ADMIN_IDS` — твой tg id
   (узнать: напиши боту /start, потом `select tg_id from users`), `CHANNEL_ID=@gaseste_casa`,
   `BOT_USERNAME=gaseste_casa_bot`, `BOOST_*`, `NUDGE_*`, `PAY_INFO`.
6. §10 шаг 5 (systemd units, enable --now) + §11 проверка (`status.sh`).
7. Если канал «потерян» (бот вылетел из админов) — вернуть админку в Telegram вручную, проверить постом.
8. Прогнать тест без денег (§11) и `/nudge`, убедиться, что выручка считается.

## 17. Ключевые якоря (числа, которые легко забыть)

| Что | Значение |
|---|---|
| Бот | `@gaseste_casa_bot`, tg bot id `8763027850`, имя «Găsește Casa | Аренда Кишинёв» |
| Канал | `@gaseste_casa` / `t.me/gaseste_casa`, бот — админ, пост-визитка = message_id `4` (закреплён) |
| Админ | `ADMIN_IDS = 1182157446` |
| Пути | код `/opt/imobiliare/bot`, venv `/opt/imobiliare/venv`, данные `/opt/imobiliare/data` |
| Сервисы | `imobiliare` (бот), `imobiliare-web` (Mini App, `127.0.0.1:8085`) |
| Продукт | Boost: `BOOST_MDL=100` MDL или `BOOST_STARS=50` ⭐ на `BOOST_DAYS=7` дней |
| Двигатель | нудж: после 2 дней, кулдаун 4 дня, проход каждые 6 ч |
| Репозиторий | `github.com/shevchenkovania-stack/gaseste_casa`, ветка `main`, пуш на каждый этап |
