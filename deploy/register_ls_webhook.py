"""Register the Lemon Squeezy webhook for us, from the server, over the LS API.

Why this exists: the webhook address is a temporary Cloudflare tunnel URL that changes on every
restart, so clicking through the LS dashboard after each change is not workable. Verified against
the LS API docs: POST /v1/webhooks needs url, events, secret (the secret is never returned later)
and a store relationship; webhooks exist separately for test mode and live mode, so we create both
and switching the store to live mode later needs no re-registration.

Reads everything from /opt/imobiliare/bot/.env, writes back only LS_WEBHOOK_SECRET, and reuses the
secret that is already there - re-running must never silently change the signature the provider uses.

Run: /opt/imobiliare/venv/bin/python /tmp/register_ls_webhook.py
"""
import asyncio
import json
import re
import secrets
import sys

sys.path.insert(0, "/opt/imobiliare/bot")

import aiohttp

import config
import lemon

ENV_PATH = "/opt/imobiliare/bot/.env"
EVENTS = ["order_created", "order_processed", "order_refunded"]
FALLBACK_EVENTS = ["order_created", "order_refunded"]


def headers() -> dict:
    return {"Accept": "application/vnd.api+json", "Content-Type": "application/vnd.api+json",
            "Authorization": f"Bearer {config.LS_API_KEY}"}


def patch_env(key: str, value: str) -> None:
    """Replace (or append) one KEY=value line in .env, leaving every other line untouched."""
    with open(ENV_PATH, encoding="utf-8") as f:
        lines = f.read().splitlines()
    pair = f"{key}={value}"
    for i, line in enumerate(lines):
        if re.match(rf"^{re.escape(key)}=", line):
            lines[i] = pair
            break
    else:
        lines.append(pair)
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f".env: {key} обновлён")


async def api(session, method: str, path: str, payload: dict | None = None):
    async with session.request(method, f"{lemon.API}{path}", json=payload, headers=headers()) as resp:
        body = await resp.text()
        try:
            data = json.loads(body)
        except ValueError:
            data = {}
        return resp.status, data, body


async def list_webhooks(session) -> list:
    status, data, _ = await api(session, "GET", f"/webhooks?filter[store_id]={config.LS_STORE_ID}")
    if status != 200:
        print(f"список вебхуков не получен ({status}) - создаём вслепую")
        return []
    rows = data.get("data") or []
    return [rows] if isinstance(rows, dict) else list(rows)


async def drop_stale(session, rows: list, current: str) -> None:
    """Forget webhooks pointing at our previous tunnel address.

    Each restart of the tunnel produces a new URL, and LS keeps delivering to the old one - those
    orders are lost silently. Anything of ours that is not the current address must go.
    """
    for w in rows:
        attrs = w.get("attributes") or {}
        if attrs.get("url", "").endswith("/webhook/lemonsqueezy") and attrs.get("url") != current:
            status, _, body = await api(session, "DELETE", f"/webhooks/{w['id']}")
            print(f"  удалён устаревший вебхук {attrs['url']} -> {status}"
                  + ("" if status in (200, 204) else f" {body[:150]}"))


async def create(session, url: str, secret: str, test_mode: bool) -> bool:
    """One webhook. If LS rejects the event list, retry with the two events it always documents."""
    for events in (EVENTS, FALLBACK_EVENTS):
        payload = {"data": {
            "type": "webhooks",
            "attributes": {"url": url, "events": events, "secret": secret, "test_mode": test_mode},
            "relationships": {"store": {"data": {"type": "stores", "id": str(config.LS_STORE_ID)}}},
        }}
        status, _, body = await api(session, "POST", "/webhooks", payload)
        if status in (200, 201):
            print(f"  вебхук создан (test_mode={test_mode}, events={events})")
            return True
        if status == 422 and "events" in body:
            print(f"  события {events} отклонены, пробую минимальный список")
            continue
        print(f"  НЕ СОЗДАНО (test_mode={test_mode}) {status}: {body[:300]}")
        return False


async def check_checkout(session) -> None:
    """Prove the API key and variant id are real by creating a checkout nobody will pay."""
    if not config.LS_VARIANT_ID:
        print("LS_VARIANT_ID пуст -> checkout не проверялся, кнопка «Картой» не включится")
        return
    try:
        checkout_id, url = await lemon.create_checkout(0, 0, expires_minutes=5)
        print(f"checkout API OK: id={checkout_id[:8]}…, url={url[:60]}… (этот чек-аут не оплачивается)")
    except Exception as e:
        print(f"checkout API НЕ РАБОТАЕТ: {e}")


async def main() -> None:
    if not config.LS_API_KEY or not config.LS_STORE_ID:
        sys.exit("Нужны LS_API_KEY и LS_STORE_ID в .env (LS: Settings -> API; id магазина в URL дашборда)")
    if not config.WEBAPP_URL.startswith("https://"):
        sys.exit("WEBAPP_URL пуст или не https - сначала запусти /tmp/apply_tunnel.sh (или apply_https.sh)")
    url = config.WEBAPP_URL.rstrip("/") + "/webhook/lemonsqueezy"
    secret = config.LS_WEBHOOK_SECRET or secrets.token_hex(24)
    print(f"webhook url : {url}")
    print("secret      : " + ("тот же, что уже в .env" if config.LS_WEBHOOK_SECRET else secret))
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25)) as session:
        rows = await list_webhooks(session)
        await drop_stale(session, rows, url)
        live_modes = {bool(w.get("attributes", {}).get("test_mode")) for w in rows
                      if w.get("attributes", {}).get("url") == url}
        for test_mode in (True, False):
            if test_mode in live_modes:
                print(f"вебхук на {url} уже есть (test_mode={test_mode}) -> не дублируем")
                continue
            await create(session, url, secret, test_mode)
        await check_checkout(session)
    patch_env("LS_WEBHOOK_SECRET", secret)
    proc = await asyncio.create_subprocess_exec("systemctl", "restart", "imobiliare-web", "imobiliare")
    await proc.wait()
    async with aiohttp.ClientSession() as session:
        async with session.post("http://127.0.0.1:8085/webhook/lemonsqueezy",
                                json={}, headers={"Content-Type": "application/json"}) as resp:
            print(f"сервисы перезапущены (exit={proc.returncode}); локальный вебхук -> {resp.status} "
                  "(401 = подпись требует, так и должно быть)")


asyncio.run(main())
