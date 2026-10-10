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
  выделяется ⭐ на `BOOST_DAYS` дней. Три рельса оплаты (порядок кнопок = порядок удобства):
  **картой `CARD_PRICE_CENTS`** через Lemon Squeezy (мерчант-оф-рекорд, работает без юрлица и без
  карты, привязанной к Telegram), **`BOOST_MDL` MDL переводом** на карту с ручным подтверждением,
  **`BOOST_STARS` Telegram Stars ⭐**.

Метрика успеха (см. MISSION.md §18): **`REAL_REVENUE > 0`** — первый реальный платёж от клиента.
Считается по таблице `payments` и **не смешивается**: `revenue_card` (всё, что не `XTR`/`MDL`/`XTEST`,
то есть USD из Lemon Squeezy), `revenue_mdl` (`currency='MDL'`), `revenue_stars` (`currency='XTR'`);
тестовые платежи (`XTEST` и `is_test=1`) в выручку не попадают.

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
  lemon.py               клиент Lemon Squeezy: создание checkout-ссылки, проверка подписи X-Signature,
                        разбор order-вебхука в карточку заказа (единственный модуль, знающий LS)
  scheduler.py           фоновые задачи: Boost-нудж (двигатель выручки) + применение карточных заказов
  requirements.txt       aiogram, aiosqlite, aiohttp, python-dotenv
  .env.example           шаблон ENV-файла (реальный .env в git не попадает)
  handlers/
    start.py             /start, /menu, deep links (?start=метка, /startapp boost:<id>), /paysupport
    add.py               FSM подачи объявления (11 состояний) + уведомление админов
    browse.py            FSM поиска (deal → ptype → district → результаты с пагинацией)
    profile.py           «Мои объявления»
    boost.py             три платёжных рельса: карта (LS checkout), Stars-инвойс, ручной перевод MDL
    admin.py             модерация, подтверждение ручных платежей, /stats /pending /nudge /broadcast
  webapp/
    app.py               aiohttp-сервер: /api/listings, /api/listing/{id}, POST .../contact, /api/stats,
                         /photos/ и POST /webhook/lemonsqueezy (входящий ящик карточных заказов)
    static/index.html    SPA-витрина (фильтры, карточка, «связаться», Boost для владельца)
deploy/                  всё, что связано с сервером и проверками (ничего не импортируется ботом)
  imobiliare.service     systemd unit бота
  imobiliare-web.service systemd unit Mini App
  nginx-chirie.conf      шаблон reverse-proxy (ждёт домен)
  apply_https.sh         домен → nginx + certbot → HTTPS для Mini App И вебхука LS (одной командой)
  apply_card.sh          / test_card_rail.py — приложить карточный рельс и проверить его без денег
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
scheduler.py (тот же процесс) ────┘  нудж + apply_card_orders         │
                                          webapp/app.py (aiohttp, 127.0.0.1:8085)
                                             ▲ читает ту же БД, пишет views/contacts
Lemon Squeezy ──POST /webhook/lemonsqueezy (HMAC)──>┘  карточка заказа в card_orders
                                             ▲
                                         SPA index.html (пока только локально)
```

Разделение ответственности в деньгах: **веб-процесс только принимает** карточные заказы (подпись →
таблица `card_orders`), **бот-процесс единственный, кто начисляет** Boost и пишет `payments`.
Так вебхук не может ни удвоить платёж, ни остаться с начислением без записи — всё решает флаг
`card_orders.applied`.

Три важных факта:

1. **Одна SQLite на два процесса.** Поэтому `PRAGMA journal_mode=WAL` и `busy_timeout=5000`
   обязательны — без них бывают `database is locked`.
2. **Бот на polling, не на webhook.** Наружу не смотрит ничего, кроме nginx, когда включён HTTPS-рельс:
   пока домена нет, `ufw` держит открытым только SSH :22. Вебхук Lemon Squeezy принимает **webapp**
   (`/webhook/lemonsqueezy`), не бот — то есть деньги приходят в процесс, который и так слушает
   127.0.0.1:8085, а бот их только начисляет.
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
| `LS_API_KEY` | пусто | ключ API Lemon Squeezy (Settings → API) | **пусто — нет аккаунта** |
| `LS_STORE_ID` | пусто | id магазина (число в URL страницы товара) | пусто |
| `LS_VARIANT_ID` | пусто | id варианта товара (Products → ваш товар → Variant ID) | пусто |
| `LS_WEBHOOK_SECRET` | пусто | signing secret из Settings → Webhooks; проверяется подпись `X-Signature` | пусто |
| `CARD_PRICE_CENTS` | `500` | цена Boost в карточке LS, **в US центах** ($5.00 ≈ 90 MDL) | `500` |
| → `CARD_ENABLED` | *(вычисляется)* | `True` только если заданы API_KEY + STORE_ID + VARIANT_ID; включает кнопку «💳 Картой» | **False** |
| `NUDGE_AFTER_DAYS` | `2` | через сколько дней после подачи напоминать про Boost | `2` |
| `NUDGE_COOLDOWN_DAYS` | `4` | как часто можно напоминать по одному объявлению | `4` |
| `NUDGE_INTERVAL_HOURS` | `6` | как часто напоминать про Boost (цикл спит **первым**, значит первый нудж не раньше 6 ч после рестарта; карточный ящик при этом опрашивается каждые 60 с) | `6` |
| `CONTACT_URL` | пусто | контакт поддержки в `/paysupport` | пусто |
| `CHANNEL_ID` | пусто → публикация в канал выключена | `@username` публичного канала или `-100...` id | `@gaseste_casa` |
| `CHANNEL_URL` | *(вычисляется)* | `https://t.me/<username>` если `CHANNEL_ID` начинается с `@` | t.me/gaseste_casa |
| `BOT_USERNAME` | пусто | для CTA-кнопок в постах канала | `gaseste_casa_bot` |
| `BOT_URL` | *(вычисляется)* | `https://t.me/<BOT_USERNAME>` | — |
| `WEBAPP_URL` | пусто → кнопка «Открыть приложение» скрыта | публичный HTTPS адрес Mini App; **он же базовый URL для вебхука Lemon Squeezy** | **пусто (нет домена)** |
| `STARS_CURRENCY` | `XTR` (константа, не ENV) | валюта Stars-инвойсов | `XTR` |

Правило: **любая новая настройка = ключ в `config.py` + строка в `.env.example` + строка в эту таблицу.**
Никаких значений, зашитых в обработчиках.

---

## 5. База данных

Схема создаётся автоматически при старте бота (`db.init_db()` → `executescript(SCHEMA)`),
дополнительные колонки — миграцией `_migrate()` в том же месте. Mini App вызывает то же самое через
`db.ensure_schema(conn)`, поэтому порядок старта сервисов не важен, а первичного создания БД руками не нужно.

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
    purpose TEXT,                  -- boost | boost_test | boost_manual | boost_card | boost_card_test
    stars INTEGER,                 -- сумма в Stars (0 для MDL и карты)
    currency TEXT,                 -- XTR | XTEST | MDL | USD (валюта карточного мерчанта)
    telegram_charge_id TEXT, provider_charge_id TEXT,  -- для карты = LS order identifier (UUID)
    amount REAL,                   -- миграция: реальная сумма в валюте платежа (MDL или USD)
    is_test INTEGER DEFAULT 0,     -- миграция: платёж в тестовом режиме провайдера
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE card_orders (         -- ВХОДЯЩИЙ ЯЩИК карточных платежей (пишет webapp, читает бот)
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT UNIQUE NOT NULL, -- LS attributes.identifier; UNIQUE = защита от дублей вебхука
    listing_id INTEGER, tg_id INTEGER,   -- прилетают из meta.custom_data checkout'а
    amount_cents INTEGER NOT NULL, currency TEXT NOT NULL, status TEXT NOT NULL,
    test_mode INTEGER NOT NULL DEFAULT 0, customer TEXT,
    applied INTEGER NOT NULL DEFAULT 0,  -- 1 = Boost уже начислен, повторно не начислить
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
- `store_card_order(conn, order)` — вызывается **webapp-ом** на его соединении; вставляет заказ,
  при `IntegrityError` (повторная доставка того же `order_id`) только обновляет `status` и возвращает
  `False` ⇒ удвоение платежа невозможно на уровне схемы;
- `card_orders_to_apply(limit=20)` → `applied=0 AND status='paid' AND listing_id IS NOT NULL`;
  `mark_card_order_applied(id)` — ставит флаг после начисления;
- `get_user_by_tg_id(tg_id)` — читает покупателя, **не создавая** его (в отличие от
  `get_or_create_user`, который затёр бы NULL-ами username/first_name);
- `stats()` — пользователи, объявления, `boosts WHERE status IN ('paid','manual')`,
  `revenue_stars` (`XTR`, `is_test=0`), `revenue_mdl` (`amount`, `MDL`, `is_test=0`),
  `revenue_card` (`amount`, валюта вне `XTR/MDL/XTEST`, `is_test=0`), `card_unapplied`
  (не начисленные оплаченные карточные заказы = **индикатор здоровья вебхука**),
  `test_payments` (`XTEST` или `is_test=1`).

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
| `boost:` | boost.py | listing_id | оффер Boost (все включённые рельсы) |
| `card:` | boost.py | listing_id | создать LS checkout и дать URL-кнопку «🔗 Открыть оплату картой» |
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

**Boost из бота:** карточка своего объявления → «🚀 Поднять (Boost)» → оффер со всеми включёнными
рельсами (карта → MDL → Stars). Чужое объявление — «Поднять можно только своё».
Карточный путь: «💳 Картой $5.00» → бот создаёт LS checkout → URL-кнопка на платёжную страницу →
покупатель платит → LS стучится вебхуком → бот сам начисляет Boost и пишет покупателю и админам.

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
| `POST /webhook/lemonsqueezy` | **подпись `X-Signature`** (не initData) | ящик карточных заказов: 401 bad signature, 400 bad json, 200 `{"ok":true,"ignored":true}` для не-order событий, иначе `{"ok":true,"recorded":true/false}` |
| `GET /photos/{file}` | — | статика из `PHOTOS_DIR` |

Валидация initData — детерминированная по документации Telegram: `secret = HMAC_SHA256(key="WebAppData", msg=BOT_TOKEN)`,
`hash = HMAC_SHA256(key=secret, msg=отсортированные "k=v\n" без hash)`, `auth_date` не старше 24 ч.
Сломанная подпись → `None` (для `/contact` это 401).

---

## 8. Деньги: три рельса + чем они ломаются

Порядок кнопок в `keyboards.boost_kb` = порядок удобства клиента: **карта → MDL → Stars**.
Текст цен везде берётся из одного места — `keyboards.rails_line()` / `boost_pitch()` (справка бота,
оффер, нудж, демо-скрипт), поэтому «переписать цену» = одна правка.

### Рельс 1 — карта (Lemon Squeezy, merchant of record)

Самый «человеческий» путь: клиент платит Visa/Mastercard на защищённой странице банка, деньги идут к LS,
LS переводит их нам на банк, а мы только получаем уведомление. Никакого эквайринг-договора,
никакого юрлица на старте, карта не привязана к Telegram.

**Почему Lemon Squeezy, а не Stripe/maib/bpay (проверено 10.10 по официальным спискам):** Stripe
не выдаёт мерчант-аккаунтов в Молдове; местный эквайринг (maib, bpay, Fastpay) требует ÎI/SRL и
договора; LS **включает Молдову в список стран для банковских выплат** мерчанту и сам закрывает
VAT/чарджбеки как merchant of record.

```
card:<id> (boost.card_offer) → проверка ownership → events.card_click
  → lemon.create_checkout(listing_id, tg_id)  # POST /v1/checkouts
       custom_price = CARD_PRICE_CENTS, enabled_variants = [LS_VARIANT_ID],
       checkout_data.custom = {listing_id, tg_id}, expires_at = +3 ч
  → events.card_checkout (meta = id checkout'а) → URL-кнопка "🔗 Открыть оплату картой"
КЛИЕНТ ПЛАТИТ → LS шлёт POST /webhook/lemonsqueezy (webapp-процесс):
  verify_signature(raw_body, X-Signature) → 401 если не совпало
  parse_order_event → card_orders (store_card_order, UNIQUE order_id) → 200
scheduler.apply_card_orders (бот-процесс, каждые 60 с, ЕДИНСТВЕННЫЙ писатель денег):
  card_orders_to_apply (applied=0 AND status='paid')
  → boost_listing(BOOST_DAYS) + boosts(status='paid', stars=0)
  → payments(purpose='boost_card', currency=USD, amount=total/100,
              provider_charge_id=order_id, is_test=test_mode)
  → mark_card_order_applied + events.boost_card_paid + ЛС покупателю + ЛС каждому админу
```

**Железные требования провайдера (иначе касса не работает):**
- **публичный HTTPS-хост обязателен.** `GET /v1/orders` не возвращает `custom_data`, то есть
  опрашивать LS список заказов бесполезно — атрибуция «какой это объект» живёт только в вебхуке.
  Поэтому рельс включён по-настоящему только после `deploy/apply_https.sh <домен>`.
- подпись — заголовок **`X-Signature`** = HMAC-SHA256 **raw body** (hex) на `LS_WEBHOOK_SECRET`.
  Хедер называется не `X-LemonSqueezy-Signature`; читать надо `await request.read()`, а не
  уже распарсенный JSON (иначе канонизация тела сломает подпись).
- отвечать **200** всегда, кроме случая плохой подписи: иначе LS ретраит доставку 3 раза.
- `custom_data` лежит в **верхнеуровневом `meta`** payload'а, а не в `data.attributes`.
- статусы заказа: `pending | failed | paid | refunded | partial_refund | fraudulent`; начисляем
  только `paid`. `test_mode=True` → начисляем Boost, но в `payments.is_test=1` и `purpose='boost_card_test'`,
  то есть в `REAL_REVENUE` такой платёж не попадает.

**Что пока не автоматизировано (осознанный долг):** возврат/чарджбек от LS не снимает уже
начисленный Boost — событие `order_refunded` сохраняется в `card_orders` (`status`), но
`applied` не откатывается. До первых реальных продаж это ручной шаг админа (снять `boosted_until`);
чинить, когда появятся возвраты.

### Рельс 2 — перевод MDL с ручным подтверждением

Работает без эквайринга, без карты в Telegram, без ÎI на старте — **страховка, если LS-аккаунта нет**.
Кнопка «💸 Переводом N MDL».

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

### Рельс 3 — Telegram Stars

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
Бесплатных прогонов два: **рельс MDL** руками (см. §11 «тест без денег») и **`deploy/test_card_rail.py`**
— он подделывает вебхук Lemon Squeezy (с честной HMAC-подписью на известном секрете) и прогоняет
весь путь кассы, ничего не оплачивая. Остальное — только реальные деньги.

### Что известно про Lemon Squeezy (проверено 10.10 по официальной документации)

| Факт | Последствие для нас |
|---|---|
| Молдова **есть** в списке стран для банковских выплат мерчанту | вывод денег на счёт возможен без ÎI на старте |
| Stripe не выдаёт мерчант-аккаунт в MD, местный эквайринг требует юрлицо | LS — единственный «как у людей» путь прямо сейчас |
| `POST /v1/checkouts` принимает `custom_price` и `checkout_data.custom` | товар в магазине нужен **один**, цена и объект — на лету |
| `GET /v1/orders` не отдаёт `custom_data` | опрос списка заказов бесполезен ⇒ вебхук и публичный HTTPS обязательны |
| вебхук-подпись = `X-Signature`, HMAC-SHA256 hex от **сырого тела** | сверять до `json.loads`, иначе подпись не сходится |
| `custom_data` в верхнеуровневом `meta` | читать `event["meta"]["custom_data"]`, а не `data.attributes` |
| нераспознанные/не-order события надо закрыть 200 | иначе LS ретраит доставку и засоряет логи |

---

## 9. Двигатель выручки (`scheduler.py`)

В том же процессе, что и бот: `asyncio.create_task(scheduler.run(bot))` рядом с `dp.start_polling`,
`job.cancel()` в `finally`. Один цикл, два ритма: **каждые `CARD_TICK_SECONDS=60` с** — `apply_card_orders`
(начисление карточных платежей), накопилось `NUDGE_INTERVAL_HOURS*3600` с — `nudge_unboosted`.
Цикл **спит первым**, поэтому после рестарта ничего не наваливается сразу. Любое исключение внутри
прохода ловится и **не убивает** цикл (`except asyncio.CancelledError: raise` выше общего `except` —
иначе задача не осталась бы отменяемой). Обе задачи пишут в лог только когда реально что-то сделали.

`nudge_unboosted(bot)`: для каждой строки из `listings_to_nudge` → владельцу ЛС с текстом
(объявление, район, цена, просмотры) и `boost_kb` (все включённые рельсы, текст из `boost_pitch()`);
`mark_nudged(listing_id)`; `events.boost_nudge`. Если ЛС недоступны (пользователь заблокировал бота) —
запись всё равно помечается, чтобы не долбить каждый проход. Вручную тот же проход: `/nudge`.

`apply_card_orders(bot)`: читает `card_orders` (`applied=0 AND status='paid'`), для каждого —
`boost_listing` + `boosts(status='paid')` + `payments` + флаг `applied=1` + уведомления покупателю и
админам. Если объявление или покупатель не найдены — строка остаётся **неприменённой**, а в `events`
летит `card_order_unmatched`: деньги не теряются, а `/stats` покажет их в `card_unapplied` как сигнал
«разбирайся руками». Повторная доставка вебхука ничего не начисляет (флаг + `UNIQUE order_id`).

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
#    /opt/imobiliare/bot/{config.py,constants.py,db.py,keyboards.py,render.py,publish.py,lemon.py,
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
LS_API_KEY=<ключ API Lemon Squeezy, Settings -> API>
LS_STORE_ID=<id магазина>
LS_VARIANT_ID=<id варианта товара>
LS_WEBHOOK_SECRET=<signing secret из Settings -> Webhooks>
CARD_PRICE_CENTS=500
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

**Публичный HTTPS (нужен и Mini App, и карточному рельсу):** остаётся один человеческий шаг —
**домен с A-записью на IP VPS**. Дальше всё делает `deploy/apply_https.sh`:

```bash
scp deploy/apply_https.sh root@<IP>:/tmp/
ssh root@<IP> "sed -i 's/\r$//' /tmp/apply_https.sh && bash /tmp/apply_https.sh imobil.<зона>"
```

Скрипт ставит nginx + certbot (если их нет), пишет site-конфиг (`/photos/` → `PHOTOS_DIR`, остальное →
`127.0.0.1:8085`), снимает дефолтный сайт, `ufw allow 'Nginx Full'`, выпускает сертификат
(`certbot --nginx --redirect`), проверяет `https://<домен>/api/stats` и ждёт **401** от
`/webhook/lemonsqueezy` (маркер «публично доступно + TLS живой + подпись требует»), правит `WEBAPP_URL`
в `.env` и перезапускает бота. После — в @BotFather: `/newapp` (или Bot Settings → Menu Button) на этот URL.
Ручной путь без скрипта: шаблон `deploy/nginx-chirie.conf` (заменить `imobil.REPLACE_ME.md`).

**Настройка Lemon Squeezy (это делает человек, бот не может):**

1. Аккаунт на lemon-squeezy.com → создать **store** → `Settings → API` → ключ → `LS_API_KEY`;
   id магазина → `LS_STORE_ID`.
2. **Products** → один товар «Boost» (любая цена — мы переопределяем её `custom_price`) → скопировать
   **Variant ID** → `LS_VARIANT_ID`.
3. Домен уже живой (см. выше) → `Settings → Webhooks → New`: callback
   `https://<домен>/webhook/lemonsqueezy`, события `order_created, order_processed, order_refunded`,
   **signing secret** → в `.env` (`LS_WEBHOOK_SECRET`) → `systemctl restart imobiliare-web`.
4. `Banking` → Молдова поддерживается как страна выплаты; вывод включается после проверки аккаунта.
5. Проверка без денег: `mode test` в LS даёт заказ с `test_mode=1` — бот начислит Boost, но
   `REAL_REVENUE` не изменится (это правильно). Боевой прогон без LS-аккаунта — `deploy/test_card_rail.py`.

Без шагов 1–3 кнопка «💳 Картой» просто не появляется (`CARD_ENABLED=False`), клиент видит MDL и Stars —
рельсы работают.

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
# обязательная проверка компиляции перед рестартом (делают apply_manual.sh / apply_card.sh)
cd /opt/imobiliare/bot && /opt/imobiliare/venv/bin/python -m py_compile \
  config.py constants.py db.py keyboards.py scheduler.py publish.py render.py main.py lemon.py \
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
`deploy/apply_nudge.sh` / `verify_nudge.sh` (нудж), `deploy/cleanup_test.sh`,
**`deploy/apply_card.sh`** (карточный рельс: компиляция включая `lemon.py`, дописывает 5 LS-ключей в
`.env`, рестартит **сначала бота** (он владеет схемой), затем веб; печатает `CARD_ENABLED`, список
обработчиков `boost`, `rails_line()`, схему `card_orders`/`payments` и делает curl вебхука — **401**
означает «роут живой, подпись требует»), **`deploy/apply_https.sh <домен>`** (см. §10).

Тесты и боевые прогоны (запускаются на сервере, самоочищаются):

- `deploy/test_money_path.py` — вызывает **боевой** `scheduler.nudge_unboosted`, админ получает ЛС
  с рабочей кнопкой; потом чистит `listings.nudged_at` и тестовые события;
- **`deploy/test_card_rail.py`** — карточный путь **без аккаунта LS и без денег**: создаёт тестовое
  объявление, подделывает `order_created` с честной HMAC-подписью, гонит его через
  `verify_signature` → `parse_order_event` → `store_card_order` (тупик дубля тоже проверяется) →
  `scheduler.apply_card_orders` и утверждает `boosted_until`, строку `payments` (5.0 USD,
  `boost_card`, `is_test=0`), `boosts.status='paid'`, `stats().revenue_card` и `card_unapplied=0`,
  после чего всё удаляет. Успех = `✅ CARD RAIL OK`;
- `deploy/make_demo.py` — удаляет старые ДЕМО-карточки, создаёт активную «ДЕМО» карточку на админе
  и шлёт админу настоящий Boost-оффер (все включённые кнопки). Не публикуется в канал;
- `deploy/post_promo.py [message_id]` — пост-визитка в канал + пин; с аргументом **редактирует**
  существующий пост вместо дубля.

**Тест рельса MDL без денег:** ДЕМО-карточка → «💸 Переводом 100 MDL»
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
| `/stats` | пользователи, объявления (активных/на модерации), Boost'ы, платежи (и число тестовых), `REAL_REVENUE Картой 💳` (+ сколько карточных заказов **не применено**), `REAL_REVENUE MDL 💰`, `REAL_REVENUE Stars ⭐` |
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
- **polling вместо webhook (для бота):** боту не нужен TLS/порт, `Restart=always` перекрывает всё.
  Входящие HTTPS-запросы принимает только webapp-процесс, и то опционально: без домена он живёт на
  127.0.0.1, а карточный рельс просто выключен.
- **Boost = колонка `boosted_until`**, а не строка-слот: истёк сам — выпал из топа, никакой очистки не нужно.
- **Фото в двух видах:** `file_id` в БД (для бота) и `{id}_{i}.jpg` в `PHOTOS_DIR` (для Mini App и поста в канал),
  потому что `file_id` нельзя отдать веб-странице.
- **Никакого скрейпинга 999.md/otakoy** (MISSION: ToS + чужие фото). Наполнение только руками/через бота;
  шаблоны текстов — в `GROWTH.md`.
- **AI только для неструктурированного** (описания, классификация фото). Деньги, БД, платежи, конечные
  автоматы —
  детерминированный код. Сейчас AI не используется вообще.
- **Карточный рельс через Lemon Squeezy (merchant of record), а не self-acquiring:** после
  `PROVIDER_ACCOUNT_INVALID`/`PAYMENT_PROVIDER_INVALID` (§8) нужен был путь, где карта клиента не
  связана с Telegram и где нам не нужно юрлицо. LS поддерживает Молдову для выплат и сам отвечает за
  VAT/чарджбеки. Отклонённые варианты: **Stripe** (не даёт мерчант-аккаунт в MD), **maib/bpay/Fastpay**
  (нужен ÎI/SRL + договор), **crypto-эквайринг** (не «как у людей», лишняя юридика, узкая аудитория),
  **опрос списка заказов `GET /v1/orders`** (не отдаёт `custom_data` ⇒ нельзя понять, какой объект оплачен).
- **Вебхук ничего не решает про деньги.** Он только кладёт строку в `card_orders`; начисление делает
  `scheduler.apply_card_orders` — единственный писатель денег для карты. Иначе два процесса гонялись бы
  за `boosted_until`, а ретрай доставки удваивал бы Boost. Цена ошибки — реальные деньги, поэтому
  детерминированный SQL и идемпотентность по `order_id`, без «умной» логики.
- **Рельс MDL с ручным подтверждением — страховка, а не основной:** решение принято после тех же ошибок
  Telegram (§8) — иначе проект стоит без платежей. Он же единственный работает совсем без провайдера.
  Юридическая оговорка: регулярные переводы физлицу = предпринимательская деятельность; после 5–20 продаж
  открывать **ÎI (ИП) / microapă** с патентом на услуги и уходить в местный эквайринг.
- **Выручка по рельсам не суммируется в одну цифру.** `payments` хранит валюту как её прислал
  провайдер (`USD` от LS, `MDL` от перевода, `XTR` от звёзд), `/stats` печатает три отдельные строки и
  `card_unapplied`. Смешивать USD и MDL в «one revenue number» — значит врать себе в метрике.
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
nginx 1.24 + certbot 2.9 **установлены**, `ufw allow 'Nginx Full'` открыт, порт 80 отвечает снаружи 200 —
не хватает только hostname с A-записью. Карточный рельс **задеплоен и проверен тестом без денег**
(`test_card_rail.py` → `✅ CARD RAIL OK`), но `CARD_ENABLED=False`: нет аккаунта Lemon Squeezy.

Не сделано, по приоритету:

1. Нет аккаунта/ключей **Lemon Squeezy** (`LS_API_KEY/LS_STORE_ID/LS_VARIANT_ID`) — кнопка «💳 Картой»
   не появляется (человеческий шаг, §10).
2. Нет **домена с A-записью** → нет HTTPS ⇒ вебхук LS физически не может приходить, Mini App недоступна
   пользователям, кнопка «Открыть приложение» скрыта. Чинится одной командой `apply_https.sh`.
3. `PAY_INFO` пустой — рельс MDL не отдаёт реквизиты покупателю (человеческий шаг).
4. 0 реальных объявлений на доске — главный блокер, не код (нужно 3–5, потом 50–100).
5. Нет бэкапов БД, сервисы от root, нет rate-limit на подачу объявлений.
6. Нет возвратов (только `/paysupport`), нет напоминаний об истёкшем Boost, `order_refunded` не снимает
   начисленный Boost (ручной шаг, §8).
7. Нет реестра источников трафика (`events.start.meta` уже пишет метки — данные есть, отчёта нет).
8. Цены рельсов не сходятся по смыслу: 50 Stars ≈ $0.5 против $5.00 картой и 100 MDL — это лазейка,
   и её закрытие (поднять `BOOST_STARS` или выключить рельс) решение человека, не кода.
9. Вывод денег: LS платит на банковском счёте после верификации аккаунта (Banking); локальный
   эквайринг MD и «нормальный учёт» по-прежнему требуют ÎI/SRL — теперь это опция, а не блокер.

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
   `BOT_USERNAME=gaseste_casa_bot`, `BOOST_*`, `NUDGE_*`, `PAY_INFO`, **`LS_*` + `CARD_PRICE_CENTS`**
   (ключи LS лежат в дашборде; `LS_WEBHOOK_SECRET` должен совпадать со значением в Settings → Webhooks,
   иначе все вебхуки будут отдавать 401 и деньги перестанут начисляться).
6. §10 шаг 5 (systemd units, enable --now) + §11 проверка (`status.sh`).
7. Если канал «потерян» (бот вылетел из админов) — вернуть админку в Telegram вручную, проверить постом.
8. Прогнать тесты без денег (§11): `test_card_rail.py` (карта) и ручной MDL-прогон через ДЕМО-карточку,
   затем `/nudge` — убедиться, что выручка считается по всем трём рельсам.
9. Если потерян домен/сертификат: купить или восстановить A-запись → `bash /tmp/apply_https.sh <домен>` →
   в LS пересохранить вебхук на новый URL (и тот же signing secret в `.env`).
   **`card_unapplied > 0` в `/stats` = заказы пришли, но не начислились** — чинить по §8.

## 17. Ключевые якоря (числа, которые легко забыть)

| Что | Значение |
|---|---|
| Бот | `@gaseste_casa_bot`, tg bot id `8763027850`, имя «Găsește Casa \| Аренда Кишинёв» |
| Канал | `@gaseste_casa` / `t.me/gaseste_casa`, бот — админ, пост-визитка = message_id `4` (закреплён) |
| Админ | `ADMIN_IDS = 1182157446` |
| Пути | код `/opt/imobiliare/bot`, venv `/opt/imobiliare/venv`, данные `/opt/imobiliare/data` |
| Сервисы | `imobiliare` (бот), `imobiliare-web` (Mini App + вебхук, `127.0.0.1:8085`) |
| Продукт | Boost на `BOOST_DAYS=7` дней: **картой `CARD_PRICE_CENTS=500` = $5.00** (LS), `BOOST_MDL=100` MDL, `BOOST_STARS=50` ⭐ |
| Вебхук карты | `POST /webhook/lemonsqueezy`, подпись `X-Signature` (HMAC-SHA256 hex от raw body), события `order_created/order_processed/order_refunded`, `custom_data = {listing_id, tg_id}` |
| LS-аккаунт | store + **один** товар (цена переопределяется `custom_price`); id магазина и variant id → `.env` |
| Checkout | живёт `POST /v1/checkouts`, `expires_at` = **+3 ч** (`expires_minutes=180`), ссылка отдаётся URL-кнопкой |
| Двигатель | нудж: после 2 дней, кулдаун 4 дня, проход каждые 6 ч; **карточный ящик — каждые 60 с** |
| Репозиторий | `github.com/shevchenkovania-stack/gaseste_casa`, ветка `main`, пуш на каждый этап |
