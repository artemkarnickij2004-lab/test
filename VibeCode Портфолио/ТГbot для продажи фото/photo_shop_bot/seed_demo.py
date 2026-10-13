"""Заполняет каталог демонстрационными работами из assets/demo.

Запуск:  python seed_demo.py
Удобно, чтобы сразу посмотреть бота «вживую», не добавляя фото вручную.
"""
import asyncio
import shutil
import uuid

import db
from config import DEMO_DIR, ORIGINALS_DIR, PREVIEWS_DIR
from watermark import make_watermark

DEMO = [
    (
        "demo1.jpg",
        "Дыхание гор",
        "Рассвет в горах: туман стекает в долину, пока вершины ловят первый свет.",
        79,
    ),
    (
        "demo2.jpg",
        "Город под дождём",
        "Ночная улица после дождя: неон, зонт и мокрый асфальт-зеркало.",
        99,
    ),
    (
        "demo3.jpg",
        "Один в поле",
        "Дерево и небо перед грозой — тишина, которую слышно.",
        59,
    ),
]


async def main() -> None:
    await db.init_db()
    added = 0
    for filename, title, description, price in DEMO:
        src = DEMO_DIR / filename
        if not src.exists():
            print(f"⚠️  {src} не найден — пропускаю")
            continue
        uid = uuid.uuid4().hex[:12]
        original = ORIGINALS_DIR / f"{uid}.jpg"
        preview = PREVIEWS_DIR / f"{uid}.jpg"
        shutil.copyfile(src, original)
        make_watermark(original, preview)
        photo_id = await db.add_photo(title, description, price, str(original), str(preview))
        added += 1
        print(f"✅ #{photo_id} «{title}» — {price} ⭐")
    print(f"\nГотово: добавлено {added} демо-работы. Откройте каталог в боте!")


if __name__ == "__main__":
    asyncio.run(main())
