# Плагины и открытый API бота

Бот расширяется без правки `bot.py`: кладёшь `.py`-файл в папку `plugins/` рядом с `bot.py`
(или в `/data/plugins` на томе Railway) — при следующем запуске он подключится сам.
Список загруженных плагинов админу покажет команда `/plugins`.

## Минимальный плагин

```python
# plugins/hello.py
def setup(api):
    async def hello(message, args):
        await message.answer(f"Привет! Ты написал: {args or '—'}")
    api.command("hello", hello, description="Тестовая команда")
```

## Что умеет `api`

| Метод | Зачем |
|---|---|
| `api.command(name, handler, description="", admin_only=False)` | команда `/name`; `handler(message, args)` |
| `api.on(event, handler)` | события `user.new`, `message.in`, `message.out`; `handler(data: dict)` |
| `api.before_ai(handler)` | `handler(ctx)` → `None`, `{"reply": "..."}` (ответить без ИИ) или `{"text": "..."}` (подменить запрос) |
| `api.system_context(provider)` | `provider(user_id)` → строка, которая добавится к системному промпту (например, данные клиента из CRM) |
| `api.http_route(method, path, handler)` | свой HTTP-эндпоинт `/api/plugins/<имя>/<path>` (например, приём данных от IoT-устройства) |
| `api.kv_get / kv_set / kv_delete` | хранилище ключ-значение для плагина (JSON) |
| `api.http_json(method, url, **kw)` | запрос к стороннему сервису (CRM, IoT-хаб), таймаут 10 с |
| `api.send(user_id, text)` | написать пользователю |
| `api.notify_admin(text)` | написать админу |
| `api.complete(messages)` | позвать ИИ бота |
| `api.env(key)` | прочитать переменную окружения (ключи сторонних сервисов храни в Railway Variables) |

Ошибки в плагине не роняют бота: они пишутся в лог.

## Внешние сервисы без кода: вебхук

Переменные Railway:

* `WEBHOOK_URL` — куда слать события (CRM, аналитика, Zapier/n8n…)
* `WEBHOOK_SECRET` — секрет; запрос подписан заголовком `X-Bot-Signature: sha256=<HMAC тела>`
* `WEBHOOK_INCLUDE_TEXT=1` — добавлять тексты сообщений (по умолчанию уходят только метаданные: id, длина)

События: `user.new`, `message.in`, `message.out`. Тело: `{"event": "...", "ts": 1700000000, "data": {...}}`.

## HTTP API

Включается переменной `API_TOKEN` (длинная случайная строка). Нужен публичный домен у сервиса на Railway.
Заголовок: `Authorization: Bearer <API_TOKEN>`.

* `GET /api/health` — проверка (без токена)
* `GET /api/stats` — `{users, messages, banned, active_24h}`
* `POST /api/send` — `{"user_id": 123, "text": "..."}` — написать существующему пользователю
* `GET /api/plugins` — список плагинов

## Приватность

Пользователи в анонимном режиме (`/incognito`) **не передаются** ни плагинам, ни вебхуку; `before_ai` и
`system_context` для них не вызываются. `/deletedata` стирает данные пользователя, включая ключи плагинов вида `u<id>:...`
(храни пользовательские данные плагина в `kv` с таким префиксом, чтобы они удалялись вместе с профилем).
