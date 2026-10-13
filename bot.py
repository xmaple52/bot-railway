#!/usr/bin/env python3
import os
import logging
import asyncio
from datetime import datetime
from typing import List, Tuple, Optional

from sqlalchemy import create_engine, Table, Column, Integer, String, Boolean, MetaData, DateTime, select, insert, update
from sqlalchemy.engine import Engine
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# Настройка логов
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ожидаемые переменные окружения
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///bot.db")

if not TELEGRAM_TOKEN:
    logger.error("TELEGRAM_TOKEN не задан. Установите переменную окружения.")
    raise SystemExit(1)

if OWNER_ID == 0:
    logger.warning("OWNER_ID не задан или равен 0. Рекомендуется указать OWNER_ID владельца бота.")

# SQLAlchemy engine
def make_engine(db_url: str) -> Engine:
    connect_args = {}
    if db_url.startswith("sqlite://"):
        connect_args = {"check_same_thread": False}
    engine = create_engine(db_url, connect_args=connect_args, future=True)
    return engine

engine = make_engine(DATABASE_URL)
metadata = MetaData()

owner_status_table = Table(
    "owner_status", metadata,
    Column("owner_id", Integer, primary_key=True),
    Column("is_premium", Boolean, nullable=False, default=False),
    Column("updated_at", DateTime, nullable=False, default=datetime.utcnow)
)

emoji_pairs_table = Table(
    "emoji_pairs", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("normal", String, nullable=False, unique=True),
    Column("premium", String, nullable=False)
)


def init_db():
    logger.info("Инициализация БД...")
    with engine.begin() as conn:
        metadata.create_all(conn)
    logger.info("БД готова.")


def db_set_owner_status_sync(owner_id: int, is_premium: bool):
    with engine.begin() as conn:
        now = datetime.utcnow()
        res = conn.execute(select(owner_status_table.c.owner_id).where(owner_status_table.c.owner_id == owner_id)).first()
        if res:
            conn.execute(
                update(owner_status_table).where(owner_status_table.c.owner_id == owner_id)
                .values(is_premium=bool(is_premium), updated_at=now)
            )
        else:
            conn.execute(
                insert(owner_status_table).values(owner_id=owner_id, is_premium=bool(is_premium), updated_at=now)
            )


def db_get_owner_status_sync(owner_id: int) -> Optional[bool]:
    with engine.connect() as conn:
        r = conn.execute(select(owner_status_table.c.is_premium).where(owner_status_table.c.owner_id == owner_id)).first()
        return bool(r[0]) if r else None


def db_add_emoji_pairs_sync(pairs: List[Tuple[str, str]]):
    with engine.begin() as conn:
        for normal, premium in pairs:
            normal = normal.strip()
            premium = premium.strip()
            if not normal or not premium:
                continue
            exists = conn.execute(select(emoji_pairs_table.c.id).where(emoji_pairs_table.c.normal == normal)).first()
            if exists:
                conn.execute(update(emoji_pairs_table).where(emoji_pairs_table.c.normal == normal).values(premium=premium))
            else:
                conn.execute(insert(emoji_pairs_table).values(normal=normal, premium=premium))


def db_list_emoji_pairs_sync() -> List[Tuple[str, str]]:
    with engine.connect() as conn:
        rows = conn.execute(select(emoji_pairs_table.c.normal, emoji_pairs_table.c.premium).order_by(emoji_pairs_table.c.id)).fetchall()
        return [(r[0], r[1]) for r in rows]


async def set_owner_status(owner_id: int, is_premium: bool):
    await asyncio.to_thread(db_set_owner_status_sync, owner_id, is_premium)
    logger.info("Owner %s premium=%s saved to DB", owner_id, is_premium)


async def get_owner_status(owner_id: int) -> Optional[bool]:
    return await asyncio.to_thread(db_get_owner_status_sync, owner_id)


async def add_emoji_pairs(pairs: List[Tuple[str, str]]):
    await asyncio.to_thread(db_add_emoji_pairs_sync, pairs)
    logger.info("Добавлено/обновлено %d пар(ы) эмодзи", len(pairs))


async def list_emoji_pairs() -> List[Tuple[str, str]]:
    return await asyncio.to_thread(db_list_emoji_pairs_sync)


def apply_emoji_replacements(text: str, owner_is_premium: bool, pairs: List[Tuple[str, str]]) -> str:
    if not text or not owner_is_premium:
        return text
    for normal, premium in pairs:
        if normal and premium:
            text = text.replace(normal, premium)
    return text


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я бот. Используй /emoji для списка эмодзи и статуса владельца.")


async def emoji_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pairs = await list_emoji_pairs()
    owner_status = await get_owner_status(OWNER_ID)
    lines = []
    if pairs:
        lines.append("Пары эмодзи (обычная -> премиум):")
        for n, p in pairs:
            lines.append(f"{n} -> {p}")
    else:
        lines.append("Пары эмодзи пока не заданы.")
    lines.append("")
    lines.append(f"Premium у владельца: {'да' if owner_status else 'нет'}")
    await update.message.reply_text("\n".join(lines))


async def addemoji_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    rest = text.partition(" ")[2].strip()
    if not rest:
        await update.message.reply_text("Отправьте после команды пары в формате: обычная пробел премиум. По нескольку в строках.")
        return
    pairs = []
    for line in rest.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 2:
            pairs.append((parts[0], parts[1]))
    if not pairs:
        await update.message.reply_text("Не распознал пары. Пример: /addemoji 🙂 ✨")
        return
    await add_emoji_pairs(pairs)
    await update.message.reply_text(f"Добавлено/обновлено {len(pairs)} пар(ы).")


async def any_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.from_user:
        return

    user = msg.from_user
    is_premium_flag = getattr(user, "is_premium", None)
    if user.id == OWNER_ID and is_premium_flag is not None:
        await set_owner_status(OWNER_ID, bool(is_premium_flag))
        logger.info("Detected owner message: owner=%s is_premium=%s", OWNER_ID, is_premium_flag)

    outgoing_text = msg.text or ""
    owner_status = await get_owner_status(OWNER_ID)
    pairs = await list_emoji_pairs()
    final_text = apply_emoji_replacements(outgoing_text, bool(owner_status), pairs)
    await msg.reply_text(final_text or "—")


async def on_startup(application):
    init_db()
    logger.info("Бот запущен, ожидание сообщений...")


def main():
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("emoji", emoji_command))
    application.add_handler(CommandHandler("addemoji", addemoji_command))
    application.add_handler(MessageHandler(filters.ALL & (~filters.COMMAND), any_message_handler))

    application.post_init = on_startup

    logger.info("Запускаем polling...")
    application.run_polling()


if __name__ == "__main__":
    main()
