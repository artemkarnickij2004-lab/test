"""Общие помощники для хэндлеров."""
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import FSInputFile, Message

import texts


async def edit_text_caption(message: Message, text: str, markup) -> Message:
    """Правит подпись (если сообщение с фото) или текст, при неудаче шлёт новое."""
    if message.photo:
        try:
            return await message.edit_caption(caption=text, reply_markup=markup)
        except TelegramBadRequest:
            pass
    try:
        return await message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest:
        return await message.answer(text, reply_markup=markup)


async def deliver_original(bot: Bot, chat_id: int, photo) -> None:
    """Отправляет покупателю оригинал (документом — без сжатия)."""
    path = Path(photo["original_path"])
    if not path.exists():
        await bot.send_message(chat_id, texts.DOCUMENT_MISSING)
        return
    await bot.send_document(
        chat_id,
        FSInputFile(path),
        caption=texts.DOC_CAPTION.format(title=photo["title"]),
    )
