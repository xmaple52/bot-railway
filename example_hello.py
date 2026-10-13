"""Пример плагина. Удали или скопируй как шаблон для своего."""


def setup(api):
    async def hello(message, args):
        count = (await api.kv_get(f"u{message.from_user.id}:hello", 0)) + 1
        await api.kv_set(f"u{message.from_user.id}:hello", count)
        await message.answer(f"Привет! Это пример плагина. Ты вызвал /hello уже {count} раз(а).")

    async def on_new_user(data):
        await api.notify_admin(f"Новый пользователь: {data['user_id']}")

    api.command("hello", hello, description="Пример команды плагина")
    api.on("user.new", on_new_user)
