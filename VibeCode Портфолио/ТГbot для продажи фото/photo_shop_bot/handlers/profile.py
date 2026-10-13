"""Личный кабинет: купленные фотографии."""
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

import db
import keyboards as kb
import texts
from handlers.common import deliver_original
from keyboards import DownloadCb, MenuCb

router = Router()


async def show_purchases(target: Message, user_id: int, edit: bool) -> None:
    rows = await db.get_user_purchases(user_id)
    if rows:
        text = texts.PURCHASES_HEAD.format(count=len(rows), word=texts.plural(len(rows)))
        markup = kb.purchases_kb(rows)
    else:
        text = texts.PURCHASES_EMPTY
        markup = kb.empty_collection()

    if edit:
        from handlers.common import edit_text_caption
        await edit_text_caption(target, text, markup)
    else:
        await target.answer(text, reply_markup=markup)


@router.message(Command("purchases"))
async def cmd_purchases(message: Message) -> None:
    await show_purchases(message, message.from_user.id, edit=False)


@router.callback_query(MenuCb.filter(F.action == "purchases"))
async def cb_purchases(callback: CallbackQuery) -> None:
    await show_purchases(callback.message, callback.from_user.id, edit=True)
    await callback.answer()


@router.callback_query(DownloadCb.filter())
async def cb_download(callback: CallbackQuery, callback_data: DownloadCb) -> None:
    photo = await db.get_photo(callback_data.photo_id)
    if not photo:
        await callback.answer(texts.NOT_FOR_SALE, show_alert=True)
        return
    if not await db.has_purchase(callback.from_user.id, photo["id"]):
        await callback.answer("Сначала купите этот кадр в каталоге ⭐", show_alert=True)
        return
    await callback.answer(texts.SENDING_ORIGINAL)
    await deliver_original(callback.bot, callback.from_user.id, photo)
