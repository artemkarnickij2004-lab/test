"""Каталог-карусель и покупка за звёзды."""
from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, FSInputFile, InputMediaPhoto, LabeledPrice, Message

import db
import keyboards as kb
import texts
from config import CURRENCY_STARS
from handlers.common import edit_text_caption
from keyboards import BuyCb, CatalogCb, MenuCb

router = Router()


def _card_markup_and_caption(photo, index: int, total: int, owned: bool):
    caption = texts.card_caption(photo, index, total, owned)
    markup = kb.catalog_card(index, total, photo["id"], photo["price_stars"], owned)
    return caption, markup


async def show_catalog(message: Message, index: int, user_id: int, edit: bool) -> None:
    photos = await db.get_active_photos()
    if not photos:
        markup = kb.back_home()
        if edit:
            await edit_text_caption(message, texts.CATALOG_EMPTY, markup)
        else:
            await message.answer(texts.CATALOG_EMPTY, reply_markup=markup)
        return

    index %= len(photos)
    photo = photos[index]
    owned = await db.has_purchase(user_id, photo["id"])
    src = photo["preview_file_id"] or FSInputFile(photo["preview_path"])
    caption, markup = _card_markup_and_caption(photo, index, len(photos), owned)

    sent = None
    if edit and message.photo:
        try:
            sent = await message.edit_media(
                media=InputMediaPhoto(media=src, caption=caption, parse_mode="HTML"),
                reply_markup=markup,
            )
        except TelegramBadRequest:
            sent = None
    if sent is None or sent is True:
        sent = await message.answer_photo(src, caption=caption, reply_markup=markup)
    if getattr(sent, "photo", None) and not photo["preview_file_id"]:
        await db.set_preview_file_id(photo["id"], sent.photo[-1].file_id)


async def refresh_card(bot: Bot, chat_id: int, message_id: int, photo_id: int) -> None:
    """Перерисовывает карточку после покупки (кнопка меняется на «Скачать»)."""
    photos = await db.get_active_photos()
    for i, p in enumerate(photos):
        if p["id"] == photo_id:
            caption, markup = _card_markup_and_caption(p, i, len(photos), owned=True)
            src = p["preview_file_id"] or FSInputFile(p["preview_path"])
            try:
                await bot.edit_message_media(
                    chat_id=chat_id,
                    message_id=message_id,
                    media=InputMediaPhoto(media=src, caption=caption, parse_mode="HTML"),
                    reply_markup=markup,
                )
            except TelegramBadRequest:
                pass
            return


@router.message(Command("catalog"))
async def cmd_catalog(message: Message) -> None:
    await show_catalog(message, 0, message.from_user.id, edit=False)


@router.callback_query(MenuCb.filter(F.action == "catalog"))
async def cb_open_catalog(callback: CallbackQuery) -> None:
    await show_catalog(callback.message, 0, callback.from_user.id, edit=True)
    await callback.answer()


@router.callback_query(CatalogCb.filter(F.action == "nav"))
async def cb_nav(callback: CallbackQuery, callback_data: CatalogCb) -> None:
    await show_catalog(callback.message, callback_data.index, callback.from_user.id, edit=True)
    await callback.answer()


@router.callback_query(CatalogCb.filter(F.action == "noop"))
async def cb_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(BuyCb.filter())
async def cb_buy(callback: CallbackQuery, callback_data: BuyCb) -> None:
    photo = await db.get_photo(callback_data.photo_id)
    if not photo or not photo["is_active"]:
        await callback.answer(texts.NOT_FOR_SALE, show_alert=True)
        return
    if await db.has_purchase(callback.from_user.id, photo["id"]):
        await callback.answer(texts.ALREADY_OWNED, show_alert=True)
        return

    payload = f"photo:{photo['id']}:{callback.message.message_id}"
    await callback.message.answer_invoice(
        title=photo["title"][:32],
        description=texts.INVOICE_DESCRIPTION.format(title=photo["title"])[:255],
        payload=payload,
        provider_token="",               # пустой = оплата звёздами Telegram
        currency=CURRENCY_STARS,
        prices=[LabeledPrice(label=photo["title"][:32], amount=photo["price_stars"])],
    )
    await callback.answer()
