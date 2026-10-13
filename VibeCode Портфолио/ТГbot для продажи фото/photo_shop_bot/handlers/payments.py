"""Оплата звёздами: подтверждение заказа и выдача товара."""
from aiogram import Bot, F, Router
from aiogram.types import Message, PreCheckoutQuery

import db
import texts
from handlers.catalog import refresh_card
from handlers.common import deliver_original

router = Router()


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery, bot: Bot) -> None:
    """Telegram спрашивает: можно ли принять оплату? Проверяем, что работа ещё продаётся."""
    parts = (query.invoice_payload or "").split(":")
    ok = len(parts) >= 2 and parts[0] == "photo" and parts[1].isdigit()
    if ok:
        photo = await db.get_photo(int(parts[1]))
        ok = bool(photo and photo["is_active"])
    if ok:
        await bot.answer_pre_checkout_query(query.id, ok=True)
    else:
        await bot.answer_pre_checkout_query(query.id, ok=False, error_message=texts.PRE_CHECKOUT_ERROR)


@router.message(F.successful_payment)
async def on_paid(message: Message, bot: Bot) -> None:
    """Оплата прошла: записываем покупку и отправляем оригинал."""
    payment = message.successful_payment
    parts = (payment.invoice_payload or "").split(":")
    photo_id = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 0
    card_message_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None

    photo = await db.get_photo(photo_id)
    if not photo:
        await message.answer(texts.PAYMENT_NOT_FOUND)
        return

    await db.add_purchase(
        user_id=message.from_user.id,
        photo_id=photo_id,
        charge_id=payment.telegram_payment_charge_id or "",
        stars=payment.total_amount,
    )
    await message.answer(texts.PAYMENT_SUCCESS.format(title=photo["title"]))
    await deliver_original(bot, message.chat.id, photo)
    if card_message_id:
        await refresh_card(bot, message.chat.id, card_message_id, photo_id)
