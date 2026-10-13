"""Инлайн-клавиатуры и фабрики callback-данных."""
from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


# ---------- callback-данные ----------

class MenuCb(CallbackData, prefix="m"):
    action: str  # home | catalog | purchases | about | admin


class CatalogCb(CallbackData, prefix="c"):
    action: str  # nav | noop
    index: int = 0


class BuyCb(CallbackData, prefix="b"):
    photo_id: int


class DownloadCb(CallbackData, prefix="d"):
    photo_id: int


class AdminCb(CallbackData, prefix="a"):
    action: str  # panel | add | list | stats


class AdminPhotoCb(CallbackData, prefix="ap"):
    photo_id: int  # удаление работы


# ---------- клавиатуры ----------

def main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🖼 Каталог", callback_data=MenuCb(action="catalog"))
    kb.button(text="🛍 Мои покупки", callback_data=MenuCb(action="purchases"))
    kb.button(text="✨ О лавке", callback_data=MenuCb(action="about"))
    if is_admin:
        kb.button(text="🛠 Админ-панель", callback_data=MenuCb(action="admin"))
    kb.adjust(1)
    return kb.as_markup()


def back_home() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🏠 В главное меню", callback_data=MenuCb(action="home"))
    return kb.as_markup()


def empty_collection() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🖼 Открыть каталог", callback_data=MenuCb(action="catalog"))
    kb.button(text="🏠 В главное меню", callback_data=MenuCb(action="home"))
    kb.adjust(1)
    return kb.as_markup()


def catalog_card(index: int, total: int, photo_id: int, price: int, owned: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="◀️", callback_data=CatalogCb(action="nav", index=(index - 1) % total))
    kb.button(text=f"{index + 1} / {total}", callback_data=CatalogCb(action="noop", index=index))
    kb.button(text="▶️", callback_data=CatalogCb(action="nav", index=(index + 1) % total))
    if owned:
        kb.button(text="📥 Скачать оригинал", callback_data=DownloadCb(photo_id=photo_id))
    else:
        kb.button(text=f"⭐ Купить за {price} ⭐", callback_data=BuyCb(photo_id=photo_id))
    kb.button(text="🏠 В главное меню", callback_data=MenuCb(action="home"))
    kb.adjust(3, 1, 1)
    return kb.as_markup()


def purchases_kb(rows) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for r in rows:
        kb.button(text=f"📥 «{r['title'][:24]}»", callback_data=DownloadCb(photo_id=r["photo_id"]))
    kb.adjust(1)
    kb.row(InlineKeyboardButton(text="🏠 В главное меню", callback_data=MenuCb(action="home").pack()))
    return kb.as_markup()


def admin_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить фото", callback_data=AdminCb(action="add"))
    kb.button(text="📋 Работы", callback_data=AdminCb(action="list"))
    kb.button(text="📊 Статистика", callback_data=AdminCb(action="stats"))
    kb.button(text="🏠 В главное меню", callback_data=MenuCb(action="home"))
    kb.adjust(1)
    return kb.as_markup()


def cancel_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✖️ Отмена", callback_data=AdminCb(action="panel"))
    return kb.as_markup()


def admin_photos_kb(photos) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for p in photos:
        kb.button(text=f"🗑 #{p['id']}", callback_data=AdminPhotoCb(photo_id=p["id"]))
    kb.adjust(4)
    kb.row(InlineKeyboardButton(text="➕ Добавить", callback_data=AdminCb(action="add").pack()))
    kb.row(InlineKeyboardButton(text="🛠 В админ-панель", callback_data=AdminCb(action="panel").pack()))
    return kb.as_markup()
