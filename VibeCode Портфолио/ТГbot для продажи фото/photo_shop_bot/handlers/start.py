"""Старт, главное меню, раздел «О лавке»."""
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, FSInputFile, InputMediaPhoto, Message

import db
import keyboards as kb
import texts
from config import ADMIN_IDS, LOGO_PATH
from handlers.common import edit_text_caption
from keyboards import MenuCb

router = Router()


async def show_home(message: Message, user_id: int, edit: bool) -> None:
    markup = kb.main_menu(is_admin=user_id in ADMIN_IDS)
    if LOGO_PATH.exists():
        file_id = await db.get_setting("logo_file_id")
        src = file_id or FSInputFile(LOGO_PATH)
        sent = None
        if edit and message.photo:
            try:
                sent = await message.edit_media(
                    media=InputMediaPhoto(media=src, caption=texts.WELCOME, parse_mode="HTML"),
                    reply_markup=markup,
                )
            except TelegramBadRequest:
                sent = None
        if sent is None or sent is True:
            sent = await message.answer_photo(src, caption=texts.WELCOME, reply_markup=markup)
        if getattr(sent, "photo", None) and not file_id:
            await db.set_setting("logo_file_id", sent.photo[-1].file_id)
    else:
        if edit:
            await edit_text_caption(message, texts.WELCOME, markup)
        else:
            await message.answer(texts.WELCOME, reply_markup=markup)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await show_home(message, message.from_user.id, edit=False)


@router.callback_query(MenuCb.filter(F.action == "home"))
async def cb_home(callback: CallbackQuery) -> None:
    await show_home(callback.message, callback.from_user.id, edit=True)
    await callback.answer()


@router.callback_query(MenuCb.filter(F.action == "about"))
async def cb_about(callback: CallbackQuery) -> None:
    await edit_text_caption(callback.message, texts.ABOUT, kb.back_home())
    await callback.answer()


@router.message(Command("admin"))
async def cmd_admin_denied(message: Message) -> None:
    """Сюда попадают только не-админы (у админов команду перехватывает admin-роутер)."""
    await message.answer(texts.NO_ACCESS)
