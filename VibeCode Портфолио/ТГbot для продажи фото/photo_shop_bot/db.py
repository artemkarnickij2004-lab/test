"""Работа с базой данных SQLite (через aiosqlite)."""
import aiosqlite

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id    INTEGER PRIMARY KEY,
    username   TEXT NOT NULL DEFAULT '',
    full_name  TEXT NOT NULL DEFAULT '',
    joined_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS photos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    price_stars     INTEGER NOT NULL,
    original_path   TEXT NOT NULL,
    preview_path    TEXT NOT NULL,
    preview_file_id TEXT,
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS purchases (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    photo_id   INTEGER NOT NULL,
    charge_id  TEXT NOT NULL DEFAULT '',
    stars      INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (user_id, photo_id)
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()


# ---------- вспомогательные ----------

async def _value(query: str, params: tuple = ()):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(query, params)
        row = await cur.fetchone()
        return row[0] if row else None


async def _rows(query: str, params: tuple = ()):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(query, params)
        return await cur.fetchall()


async def _row(query: str, params: tuple = ()):
    rows = await _rows(query, params)
    return rows[0] if rows else None


async def _exec(query: str, params: tuple = ()) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(query, params)
        await db.commit()
        return cur.lastrowid or 0


# ---------- пользователи ----------

async def upsert_user(user_id: int, username: str = "", full_name: str = "") -> None:
    await _exec(
        """
        INSERT INTO users (user_id, username, full_name) VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET username = excluded.username, full_name = excluded.full_name
        """,
        (user_id, username, full_name),
    )


# ---------- фотографии ----------

async def add_photo(title: str, description: str, price_stars: int, original_path: str, preview_path: str) -> int:
    return await _exec(
        "INSERT INTO photos (title, description, price_stars, original_path, preview_path) VALUES (?, ?, ?, ?, ?)",
        (title, description, price_stars, original_path, preview_path),
    )


async def get_photo(photo_id: int):
    return await _row("SELECT * FROM photos WHERE id = ?", (photo_id,))


async def get_active_photos():
    return await _rows("SELECT * FROM photos WHERE is_active = 1 ORDER BY id DESC")


async def get_all_photos():
    return await _rows("SELECT * FROM photos ORDER BY id DESC")


async def deactivate_photo(photo_id: int) -> None:
    await _exec("UPDATE photos SET is_active = 0 WHERE id = ?", (photo_id,))


async def set_preview_file_id(photo_id: int, file_id: str) -> None:
    await _exec("UPDATE photos SET preview_file_id = ? WHERE id = ?", (file_id, photo_id))


# ---------- покупки ----------

async def add_purchase(user_id: int, photo_id: int, charge_id: str, stars: int) -> None:
    await _exec(
        "INSERT OR IGNORE INTO purchases (user_id, photo_id, charge_id, stars) VALUES (?, ?, ?, ?)",
        (user_id, photo_id, charge_id, stars),
    )


async def has_purchase(user_id: int, photo_id: int) -> bool:
    return bool(await _value("SELECT 1 FROM purchases WHERE user_id = ? AND photo_id = ?", (user_id, photo_id)))


async def get_user_purchases(user_id: int):
    return await _rows(
        """
        SELECT p.id AS photo_id, p.title, p.price_stars, pu.created_at
        FROM purchases pu
        JOIN photos p ON p.id = pu.photo_id
        WHERE pu.user_id = ?
        ORDER BY pu.id DESC
        """,
        (user_id,),
    )


# ---------- статистика ----------

async def get_stats() -> dict:
    return {
        "photos": await _value("SELECT COUNT(*) FROM photos WHERE is_active = 1") or 0,
        "users": await _value("SELECT COUNT(*) FROM users") or 0,
        "sales": await _value("SELECT COUNT(*) FROM purchases") or 0,
        "stars": await _value("SELECT COALESCE(SUM(stars), 0) FROM purchases") or 0,
    }


# ---------- настройки (кэш file_id) ----------

async def get_setting(key: str):
    return await _value("SELECT value FROM settings WHERE key = ?", (key,))


async def set_setting(key: str, value: str) -> None:
    await _exec(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
