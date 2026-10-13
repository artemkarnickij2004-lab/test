# -*- coding: utf-8 -*-
"""
Парсер уроков LMS Algoritmika (lms.algoritmika.org) для загрузки в «Мой планер».

Что делает:
  1. Открывает LMS. Если вы не авторизованы — ждёт, пока вы войдёте вручную
     в открывшемся окне (логин сохраняется в папке algoritmika_profile).
  2. Сам переходит во вкладку «Группы», вводит вашу фамилию в фильтр
     «Преподаватель» и нажимает поиск. Если интерфейс не поддался —
     ждёт, пока вы настроите фильтр вручную, и подхватывает таблицу сам.
  3. Собирает ваши группы (GROUP_IDS ниже или все со страницы).
  4. Заходит на страницу каждой группы и вытаскивает уроки: дату, время,
     название («M1У3. Создаём основу для истории»), тип, площадку.
  5. Сохраняет algoritmika_schedule.csv в формате, который понимает планер
     (даты ДД.ММ.ГГГГ, день недели вычисляется по календарю).

Установка:
    pip install playwright beautifulsoup4
    playwright install chromium

Запуск:
    python parse_algoritmika.py

Затем в планере: раздел «Расписание» → «Загрузить CSV» → algoritmika_schedule.csv
"""

import csv
import os
import re
import time
from datetime import datetime

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# ---------------------------------------------------------------------------
# НАСТРОЙКИ
# ---------------------------------------------------------------------------
BASE_URL = "https://lms.algoritmika.org"
GROUPS_PATH = "/group"
# страницы самих групп живут на backoffice
BACKOFFICE_URL = "https://backoffice.algoritmika.org"

# Ваша фамилия — подставляется в фильтр «Преподаватель» и в колонку CSV
TEACHER = "Карницкий"

# Полная ссылка со встроенными фильтрами (преподаватель + активные группы)
GROUPS_URL = (
    BASE_URL + GROUPS_PATH + "?"
    "GroupSearch%5Bid%5D=&GroupSearch%5Btitle%5D=&GroupSearch%5Bvenue%5D="
    "&GroupSearch%5Bactive_student_count%5D=&GroupSearch%5BnextLessonTime%5D="
    "&GroupSearch%5BnextLessonNumber%5D=&GroupSearch%5BnextLessonTitle%5D="
    f"&GroupSearch%5Bteacher%5D={TEACHER}&GroupSearch%5Bcurator%5D="
    "&GroupSearch%5Bstatus%5D=&GroupSearch%5Bstatus%5D%5B%5D=active"
    "&GroupSearch%5Bstatus%5D%5B%5D=recruiting&GroupSearch%5Bis_online%5D="
    "&presetType=all"
)

# Ваши группы. Оставьте список пустым [], чтобы брать ВСЕ группы со страницы.
GROUP_IDS = [
    "98786367", "98784651", "98779745", "98777914",
    "98777913", "98777912", "98772680", "98772679",
    "98756411", "98788480",
]

OUTPUT_CSV = "algoritmika_schedule.csv"
PROFILE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "algoritmika_profile")
HEADLESS = False               # True — без окна браузера (только если уже вошли раньше)

WEEKDAYS_RU = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]

# «11.10.2026 18:00»
DT_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})\s+(\d{1,2}):(\d{2})")
# название урока вида «M1У3. Создаём основу для истории» / «М1 У5. ...»
LESSON_RE = re.compile(r"[MМ]\s?\d+\s?У\s?\d+\.?\s*[^\n,;|]{0,120}")
GROUP_TYPES = ("Индивидуальная", "Мастер-класс", "Группа")


def collapse(s):
    return re.sub(r"\s+", " ", s or "").strip()


def safe_content(page):
    """HTML страницы с защитой от гонки «страница прямо сейчас переходит»."""
    for _ in range(4):
        try:
            return page.content()
        except Exception:
            time.sleep(1.5)
    return ""


# ---------------------------------------------------------------------------
# Вход в LMS
# ---------------------------------------------------------------------------
def wait_for_login(page, timeout_sec=300):
    if page.locator('input[type="password"]').count() == 0:
        return True
    print("🔐 Откройте окно браузера и войдите в LMS вручную.")
    print("   (скрипт продолжит сам, как только вы войдёте; жду до 5 минут)")
    try:
        page.wait_for_selector('input[type="password"]', state="detached",
                               timeout=timeout_sec * 1000)
    except Exception:
        pass
    time.sleep(2)
    return page.locator('input[type="password"]').count() == 0


# ---------------------------------------------------------------------------
# Навигация к таблице групп + фильтр по преподавателю
# ---------------------------------------------------------------------------
def click_groups_tab(page):
    """Кликаем вкладку/пункт меню «Группы»."""
    for sel in ['nav a:has-text("Группы")', 'a:has-text("Группы")',
                'button:has-text("Группы")', 'text=Группы']:
        try:
            loc = page.locator(sel).first
            if loc.count():
                loc.click(timeout=5000)
                time.sleep(2)
                return True
        except Exception:
            continue
    return False


def apply_teacher_filter(page):
    """Вводит фамилию в фильтр преподавателя и отправляет форму."""
    candidates = [
        'input[name="GroupSearch[teacher]"]',
        'input[name*="teacher"]',
        'input[placeholder*="реподават"]',
        'xpath=//label[contains(., "Преподаватель")]//input',
        'xpath=//label[contains(., "Преподаватель")]/following::input[1]',
        'xpath=//*[contains(text(), "Преподаватель")]/following::input[1]',
    ]
    inp = None
    for sel in candidates:
        try:
            loc = page.locator(sel).first
            if loc.count():
                inp = loc
                break
        except Exception:
            continue
    if inp is None:
        print("   ⚠️ Поле фильтра преподавателя не найдено на странице.")
        return False
    try:
        inp.click()
        inp.fill(TEACHER)
    except Exception as e:
        print("   ⚠️ Не удалось заполнить фильтр:", e)
        return False
    time.sleep(0.7)

    # жмём кнопку поиска («Найти» и т.п.), иначе — Enter в поле
    for btn in ("Найти", "Показать", "Применить", "Искать", "Поиск", "Search"):
        try:
            b = page.locator(f'button:has-text("{btn}"), input[type="submit"]').first
            if b.count() and b.is_visible():
                b.click(timeout=4000)
                time.sleep(2.5)
                return True
        except Exception:
            continue
    try:
        inp.press("Enter")
        time.sleep(2.5)
        return True
    except Exception:
        return False


def parse_listing(html):
    """Разбирает таблицу групп. Возвращает список словарей."""
    soup = BeautifulSoup(html, "html.parser")
    groups = []

    # вариант 1: нормальная таблица <tr>/<td>
    for row in soup.find_all("tr"):
        cells = [collapse(c.get_text(" ")) for c in row.find_all("td")]
        if not cells:
            continue
        row_text = " | ".join(cells)
        m_id = re.search(r"\b(9\d{7})\b", row_text)
        if not m_id:
            continue
        m_dt = DT_RE.search(row_text)
        a = row.find("a", href=True)
        groups.append({
            "id": m_id.group(1),
            "title": cells[1] if len(cells) > 1 else "",
            "venue": cells[2] if len(cells) > 2 else "",
            "type": next((t for t in GROUP_TYPES if t in row_text), "Группа"),
            "next_dt": m_dt.group(0) if m_dt else "",
            "next_title": next((c for c in cells if LESSON_RE.search(c)), ""),
            "href": a["href"] if a else None,
        })

    # вариант 2: если таблицы нет (div-вёрстка) — ищем строки-блоки
    if not groups:
        seen = set()
        for tag in soup.find_all(["div", "tr", "li", "section"]):
            txt = collapse(tag.get_text(" "))
            if not txt or len(txt) > 600:
                continue
            m_id = re.search(r"\b(9\d{7})\b", txt)
            m_dt = DT_RE.search(txt)
            if not (m_id and m_dt):
                continue
            gid = m_id.group(1)
            if gid in seen:
                continue
            seen.add(gid)
            a = tag.find("a", href=True)
            lm = LESSON_RE.search(txt)
            groups.append({
                "id": gid,
                "title": "",
                "venue": "",
                "type": next((t for t in GROUP_TYPES if t in txt), "Группа"),
                "next_dt": m_dt.group(0),
                "next_title": collapse(lm.group(0)) if lm else "",
                "href": a["href"] if a else None,
            })
    return groups


def wait_for_groups(page, timeout_sec):
    """Ждёт, пока в DOM появится таблица групп с данными."""
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        groups = parse_listing(safe_content(page))
        if groups:
            return groups
        time.sleep(3)
    return []


# ---------------------------------------------------------------------------
# Разбор страницы одной группы
# ---------------------------------------------------------------------------
# Тултип квадратика посещаемости: «3. M2У1 Введение в мобильную разработку\nср 07.10.26 17:00»
TITLE_RE = re.compile(
    r"\d+\.\s*(?P<name>.+?)\s*(?P<dow>[а-яa-z]{2})\s+"
    r"(?P<d>\d{1,2})\.(?P<mo>\d{1,2})\.(?P<y>\d{2,4})\s+"
    r"(?P<h>\d{1,2}):(?P<mi>\d{2})",
    re.S,
)


def norm_dt(d, mo, y, h, mi):
    d, mo, y, h, mi = int(d), int(mo), int(y), int(h), int(mi)
    if y < 100:
        y += 2000
    return datetime(y, mo, d, h, mi)


def parse_group_page(html):
    soup = BeautifulSoup(html, "html.parser")
    lessons = []
    seen = set()

    # 1) основной источник: тултипы квадратиков посещаемости (атрибут title)
    for tag in soup.find_all(attrs={"title": True}):
        m = TITLE_RE.search(tag["title"] or "")
        if not m:
            continue
        name = collapse(m["name"])
        # берём только тултипы с кодом урока (M1У1, M2У3...) — отсеиваем служебные
        if not re.search(r"[MМ]\s?\d+\s?У", name):
            continue
        dt = norm_dt(m["d"], m["mo"], m["y"], m["h"], m["mi"])
        key = (dt, name)
        if key in seen:
            continue  # один и тот же урок у каждого ученика — берём один раз
        seen.add(key)
        lessons.append({"dt": dt, "title": name})

    # 2) запасной вариант: «след. урок» в карточке группы
    if not lessons:
        txt = collapse(soup.get_text(" "))
        m = re.search(r"след\.\s*урок\s*(\d{1,2})\.(\d{1,2})\.(\d{2,4})\s+(\d{1,2}):(\d{2})", txt)
        if m:
            lessons.append({"dt": norm_dt(*m.groups()), "title": ""})

    # 3) запасной вариант: даты рядом с кодами уроков («M1У3. ...»)
    if not lessons:
        for s in soup.find_all(string=DT_RE):
            m = DT_RE.search(s)
            if not m:
                continue
            key = m.group(0)
            if key in seen:
                continue
            node = s.parent
            txt = ""
            for _ in range(6):
                if node is None:
                    break
                txt = collapse(node.get_text(" "))
                if 30 <= len(txt) <= 1500 and LESSON_RE.search(txt):
                    break
                node = node.parent
            if not txt or not LESSON_RE.search(txt):
                continue
            seen.add(key)
            lm = LESSON_RE.search(txt)
            lessons.append({"dt": to_datetime(key), "title": collapse(lm.group(0))})

    lessons.sort(key=lambda l: l["dt"])
    return lessons


# ---------------------------------------------------------------------------
# Вкладка «Уроки и расписание»: таблица «# | Время | Урок | Статус»
# ---------------------------------------------------------------------------
DATE_SLASH_RE = re.compile(r"(\d{1,2})[./](\d{1,2})[./](\d{2,4})\s+(\d{1,2}):(\d{2})")


def open_schedule_tab(page):
    for sel in ['a:has-text("Уроки и расписание")',
                'button:has-text("Уроки и расписание")',
                'div[role="tab"]:has-text("Уроки и расписание")',
                'text=Уроки и расписание']:
        try:
            loc = page.locator(sel).first
            if loc.count():
                loc.click(timeout=5000)
                time.sleep(2.5)
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass
                return True
        except Exception:
            continue
    return False


def parse_schedule_tab(html):
    soup = BeautifulSoup(html, "html.parser")
    lessons = []
    seen = set()
    for row in soup.find_all("tr"):
        # дата может лежать в value поля ввода — собираем текст + value инпутов
        txt = collapse(row.get_text(" "))
        date_src = txt
        for inp in row.find_all("input"):
            v = inp.get("value") or ""
            if DATE_SLASH_RE.search(v):
                date_src += " " + v
        m = DATE_SLASH_RE.search(date_src)
        if not m:
            continue  # строки-заголовки модулей («ПОВТОРЕНИЕ») пропускаются сами
        dt = norm_dt(m.group(1), m.group(2), m.group(3), m.group(4), m.group(5))

        title = ""
        for a in row.find_all("a"):
            t = collapse(a.get_text(" "))
            if re.search(r"[MМ]\s?\d+\s?У", t) or len(t) > 12:
                title = t
                break
        if not title:
            cells = [collapse(c.get_text(" ")) for c in row.find_all("td")]
            title = next((c for c in cells if LESSON_RE.search(c)), "")
        if not title:
            continue  # строка без темы урока — это не урок (логи, служебное)

        key = (dt, title)
        if key in seen:
            continue
        seen.add(key)
        lessons.append({"dt": dt, "title": title})
    lessons.sort(key=lambda l: l["dt"])
    return lessons


def to_datetime(raw):
    d, mo, y, h, mi = (int(x) for x in DT_RE.search(raw).groups())
    return datetime(y, mo, d, h, mi)


# ---------------------------------------------------------------------------
# Основная логика
# ---------------------------------------------------------------------------
def main():
    out_rows = []

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            PROFILE_DIR,
            headless=HEADLESS,
            locale="ru-RU",
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"),
        )
        page = context.pages[0] if context.pages else context.new_page()

        print("Переход на страницу групп...")
        try:
            page.goto(BASE_URL + GROUPS_PATH, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"Ошибка перехода: {e}")
            context.close()
            return

        if not wait_for_login(page):
            print("Не удалось дождаться входа. Попробуйте ещё раз.")
            context.close()
            return
        time.sleep(2)

        # --- вкладка «Группы» + фильтр по преподавателю ---
        print("Открываем вкладку «Группы»...")
        click_groups_tab(page)
        time.sleep(1.5)

        # сессия уже активна — переходим по полной ссылке со встроенными фильтрами
        print("Открываем страницу групп с фильтрами...")
        try:
            page.goto(GROUPS_URL, wait_until="domcontentloaded", timeout=60000)
        except Exception:
            pass
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        time.sleep(2)

        print(f"Применяем фильтр по преподавателю: {TEACHER}...")
        apply_teacher_filter(page)

        print("Ждём таблицу групп...")
        groups = wait_for_groups(page, 20)

        if not groups:
            # не получилось автоматически — ждём ручных действий пользователя
            print("⚠️ Таблица не появилась автоматически.")
            print("   Перейдите во вкладку «Группы» и задайте фильтр вручную —")
            print("   скрипт подхватит таблицу сам (жду до 3 минут).")
            groups = wait_for_groups(page, 180)

        print(f"Групп на странице: {len(groups)}")
        if not groups:
            print("❌ Таблица групп так и не появилась.")
            context.close()
            return

        if GROUP_IDS:
            picked = [g for g in groups if g["id"] in GROUP_IDS]
            # группы, которых не оказалось в списке, — идём на их страницы напрямую
            found = {g["id"] for g in picked}
            for gid in GROUP_IDS:
                if gid not in found:
                    picked.append({"id": gid, "title": "", "venue": "", "type": "Группа",
                                   "next_dt": "", "next_title": "", "href": None})
            groups = picked or groups

        for g in groups:
            href = g["href"] or f"{BACKOFFICE_URL}/group/view/{g['id']}#group-student-grid"
            url = href if href.startswith("http") else BASE_URL + href
            print(f"→ группа {g['id']} {g['title'] or ''}")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                time.sleep(2.5)
            except Exception as e:
                print("   ошибка перехода:", e)
                continue

            # вдруг сессия слетела — ждём ручного входа и возвращаемся
            if not wait_for_login(page, 180):
                print("   нет входа, пропускаю группу")
                continue

            open_schedule_tab(page)
            html = safe_content(page)
            lessons = parse_schedule_tab(html) or parse_group_page(html)
            print(f"   уроков найдено: {len(lessons)}")

            # если на странице группы ничего не нашли — берём ближайший урок из списка
            if not lessons and g["next_dt"]:
                lessons = [{"dt": to_datetime(g["next_dt"]), "title": g["next_title"]}]

            for l in lessons:
                out_rows.append({
                    "dt": l["dt"],
                    "group": g,
                    "lesson_title": l["title"],
                })

        context.close()

    if not out_rows:
        print("❌ Не найдено ни одного урока.")
        return

    out_rows.sort(key=lambda r: r["dt"])

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Время", "Дата", "Дисциплина", "Вид занятия",
                    "Здание / Аудитория", "Преподаватель", "День недели"])
        for r in out_rows:
            dt, g = r["dt"], r["group"]
            subject = r["lesson_title"]
            if g["title"]:
                subject = f"{subject} · {g['title']}" if subject else g["title"]
            w.writerow([
                dt.strftime("%H:%M"),
                dt.strftime("%d.%m.%Y"),
                subject,
                g["type"],
                g["venue"],
                TEACHER,
                WEEKDAYS_RU[dt.weekday()],
            ])

    print(f"\n✅ Готово! Сохранено {len(out_rows)} уроков в {OUTPUT_CSV}")
    print("Загрузите файл в планер: Расписание → «Загрузить CSV».")
    print("\n--- Ближайшие 5 уроков ---")
    for r in out_rows[:5]:
        print(" ", r["dt"].strftime("%d.%m.%Y %H:%M"), "|",
              r["lesson_title"] or r["group"]["title"])


if __name__ == "__main__":
    main()
