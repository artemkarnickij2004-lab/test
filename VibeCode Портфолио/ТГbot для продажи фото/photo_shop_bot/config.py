"""Настройки бота. Значения подхватываются из файла .env"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# === Обязательные настройки (файл .env) ===
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# ID администраторов через запятую, например: ADMIN_IDS=123456789,987654321
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").replace(";", ",").split(",") if x.strip().isdigit()}

# === Необязательные настройки ===
SHOP_NAME = os.getenv("SHOP_NAME", "ЛУМИН")
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "@username")

CURRENCY_STARS = "XTR"          # валюта Telegram Stars (для цифровых товаров — единственная разрешённая)
MIN_PRICE = 1                   # минимальная цена в звёздах
MAX_PRICE = 10_000              # максимальная цена в звёздах

# === Пути (менять обычно не нужно) ===
BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "storage"
ORIGINALS_DIR = STORAGE_DIR / "originals"
PREVIEWS_DIR = STORAGE_DIR / "previews"
DB_PATH = STORAGE_DIR / "shop.db"
LOGO_PATH = BASE_DIR / "assets" / "logo.png"
DEMO_DIR = BASE_DIR / "assets" / "demo"

for _d in (STORAGE_DIR, ORIGINALS_DIR, PREVIEWS_DIR):
    _d.mkdir(parents=True, exist_ok=True)
