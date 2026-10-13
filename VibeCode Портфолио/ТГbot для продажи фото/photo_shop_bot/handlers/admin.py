"""Админ-панель: добавление, список и удаление работ, статистика."""
import mimetypes
import uuid
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.filters import BaseFilter, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

import db
import keyboards as kb
import texts
from config import ADMIN_IDS, MAX_PRICE, MIN_PRICE, ORIGINALS_DIR, PREVIEWS_DIR
from handlers.common import edit_text_caption
from keyboards import AdminCb, AdminPhotoCb, MenuCb
from states import AddPhoto
from watermark import make_watermark

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp"}


class IsAdmin(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        return bool(event.from_user) and event.from_user.id in ADMIN_IDS


router = Router()
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


# ---------- панель ----------

async def show_panel(target: Message | CallbackQuery) -> None:
    if isinstance(target, CallbackQuery):
        await edit_text_caption(target.message, texts.ADMIN_PANEL, kb.admin_menu())
        await target.answer()
    else:
        await target.answer(texts.ADMIN_PANEL, reply_markup=kb.admin_menu())


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    await show_panel(message)


@router.callback_query(MenuCb.filter(F.action == "admin"))
@router.callback_query(AdminCb.filter(F.action == "panel"))
async def cb_panel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await show_panel(callback)


# ---------- добавление фото ----------

@router.callback_query(AdminCb.filter(F.action == "add"))
async def cb_add(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddPhoto.image)
    await edit_text_caption(callback.message, texts.ADMIN_ASK_PHOTO, kb.cancel_kb())
    await callback.answer()


@router.message(AddPhoto.image, F.photo | F.document)
async def add_image(message: Message, state: FSMContext, bot: Bot) -> None:
    ext = ".jpg"
    if message.photo:
        file_id = message.photo[-1].file_id
    else:
        doc = message.document
        if not doc.mime_type or not doc.mime_type.startswith("image/"):
            await message.answer(texts.ADMIN_BAD_PHOTO, reply_markup=kb.cancel_kb())
            return
        file_id = doc.file_id
        ext = Path(doc.file_name).suffix.lower() if doc.file_name else (mimetypes.guess_extension(doc.mime_type) or ".jpg")
        if ext == ".jpe":
            ext = ".jpg"
        if ext not in ALLOWED_EXT:
            ext = ".jpg"

    uid = uuid.uuid4().hex[:12]
    original_path = ORIGINALS_DIR / f"{uid}{ext}"
    preview_path = PREVIEWS_DIR / f"{uid}.jpg"

    try:
        tg_file = await bot.get_file(file_id)
        await bot.download_file(tg_file.file_path, destination=original_path)
        make_watermark(original_path, preview_path)
    except Exception:
        await message.answer(texts.ADMIN_FILE_FAIL, reply_markup=kb.cancel_kb())
        return

    await state.update_data(original=str(original_path), preview=str(preview_path))
    await state.set_state(AddPhoto.title)
    await message.answer(texts.ADMIN_ASK_TITLE, reply_markup=kb.cancel_kb())


@router.message(AddPhoto.image)
async def add_image_wrong(message: Message) -> None:
    await message.answer(texts.ADMIN_BAD_PHOTO, reply_markup=kb.cancel_kb())


@router.message(AddPhoto.title, F.text)
async def add_title(message: Message, state: FSMContext) -> None:
    title = message.text.strip().strip("«»\"'")
    if not (1 <= len(title) <= 60):
        await message.answer(texts.ADMIN_BAD_TITLE, reply_markup=kb.cancel_kb())
        return
    await state.update_data(title=title)
    await state.set_state(AddPhoto.description)
    await message.answer(texts.ADMIN_ASK_DESC, reply_markup=kb.cancel_kb())


@router.message(AddPhoto.description, F.text)
async def add_description(message: Message, state: FSMContext) -> None:
    raw = message.text.strip()
    description = "" if raw in {"-", "—"} else raw[:350]
    await state.update_data(description=description)
    await state.set_state(AddPhoto.price)
    await message.answer(texts.ADMIN_ASK_PRICE, reply_markup=kb.cancel_kb())


@router.message(AddPhoto.price, F.text)
async def add_price(message: Message, state: FSMContext) -> None:
    try:
        price = int(message.text.strip().replace(" ", ""))
    except ValueError:
        price = 0
    if not (MIN_PRICE <= price <= MAX_PRICE):
        await message.answer(texts.ADMIN_BAD_PRICE, reply_markup=kb.cancel_kb())
        return

    data = await state.get_data()
    photo_id = await db.add_photo(
        title=data["title"],
        description=data.get("description", ""),
        price_stars=price,
        original_path=data["original"],
        preview_path=data["preview"],
    )
    await state.clear()
    await message.answer_photo(
        FSInputFile(data["preview"]),
        caption=texts.ADMIN_SAVED.format(id=photo_id, title=data["title"], price=price),
        reply_markup=kb.admin_menu(),
    )


# ---------- список и удаление ----------

@router.callback_query(AdminCb.filter(F.action == "list"))
async def cb_list(callback: CallbackQuery) -> None:
    photos = await db.get_all_photos()
    active = [p for p in photos if p["is_active"]]
    if not active:
        await edit_text_caption(callback.message, texts.ADMIN_LIST_EMPTY, kb.admin_menu())
        await callback.answer()
        return
    lines = [texts.ADMIN_LIST_HEAD.format(count=len(active))]
    for p in active:
        lines.append(f"#{p['id']} · «{p['title']}» — {p['price_stars']} ⭐")
    lines.append(texts.ADMIN_LIST_FOOTER)
    await edit_text_caption(callback.message, "\n".join(lines), kb.admin_photos_kb(active))
    await callback.answer()


@router.callback_query(AdminPhotoCb.filter())
async def cb_delete_photo(callback: CallbackQuery, callback_data: AdminPhotoCb, state: FSMContext) -> None:
    photo = await db.get_photo(callback_data.photo_id)
    if not photo:
        await callback.answer(texts.ADMIN_NOT_FOUND, show_alert=True)
        return
    await db.deactivate_photo(photo["id"])
    await callback.answer(texts.ADMIN_DELETED.format(id=photo["id"]), show_alert=True)
    await cb_list(callback)


# ---------- статистика ----------

@router.callback_query(AdminCb.filter(F.action == "stats"))
async def cb_stats(callback: CallbackQuery) -> None:
    stats = await db.get_stats()
    await edit_text_caption(callback.message, texts.ADMIN_STATS.format(**stats), kb.admin_menu())
    await callback.answer()
