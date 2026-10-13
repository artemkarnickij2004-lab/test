"""Точка входа: запуск бота (long polling)."""
import asyncio
import logging

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

import db
from config import BOT_TOKEN
from handlers import admin, catalog, payments, profile, start

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
log = logging.getLogger("lumin")


class TrackUsersMiddleware(BaseMiddleware):
    """Запоминает каждого, кто пишет боту (для статистики)."""

    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if user is not None:
            try:
                await db.upsert_user(user.id, user.username or "", user.full_name or "")
            except Exception as exc:  # статистика не должна ронять бота
                log.warning("upsert_user: %s", exc)
        return await handler(event, data)


async def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit(
            "❗ Не задан BOT_TOKEN.\n"
            "Скопируйте .env.example в .env и впишите токен от @BotFather."
        )

    await db.init_db()

    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.update.outer_middleware(TrackUsersMiddleware())
    dp.include_routers(
        admin.router,      # первым: перехватывает команды админа
        payments.router,   # pre_checkout и successful_payment
        catalog.router,    # каталог и покупка
        profile.router,    # личный кабинет
        start.router,      # /start, меню, «О лавке»
    )

    await bot.delete_webhook(drop_pending_updates=True)
    me = await bot.get_me()
    log.info("Бот @%s запущен ✦ Останавливается по Ctrl+C", me.username)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit) as e:
        if isinstance(e, SystemExit) and e.code:
            print(e)
        log.info("Бот остановлен.")
