from playwright.sync_api import sync_playwright
import csv
from bs4 import BeautifulSoup
import time
import re

def parse_kai_sorted_week():
    group_number = "3436"
    search_prefix = "343"
    url = "https://kai.ru/web/studentu/raspisanie1"
    
    # Список дней недели для поиска и сортировки
    days_of_week = ['понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье']
    # Словарь для сортировки: Понедельник=0, Вторник=1 и т.д.
    day_order = {day: i for i, day in enumerate(days_of_week)}
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False) 
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        print("Переход на страницу...")
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
        except Exception as e:
            print(f"Ошибка перехода: {e}")
            browser.close()
            return

        # --- ШАГ 1: Реклама ---
        print("Ждем рекламу (5 сек)...")
        time.sleep(5)
        try:
            page.evaluate("""() => {
                const elements = document.querySelectorAll('button, a, span, div');
                for (let el of elements) {
                    const text = el.textContent.trim();
                    const rect = el.getBoundingClientRect();
                    if ((text === '×' || text === '✕' || text === 'X') && rect.width < 50 && rect.height < 50) {
                        el.click();
                        return true;
                    }
                }
                return false;
            }""")
            print("Реклама закрыта.")
        except:
            print("Не удалось закрыть рекламу автоматически, продолжаем...")

        # --- ШАГ 2: Ввод "343" ---
        try:
            page.evaluate("""() => {
                const labels = document.querySelectorAll('label, span, div, p');
                for (let el of labels) {
                    if (el.textContent.includes('Введите номер группы')) {
                        const container = el.parentElement || el.closest('div');
                        if (container) {
                            const input = container.querySelector('input');
                            if (input) { input.focus(); input.click(); return true; }
                        }
                    }
                }
                const input = document.querySelector('input[type="text"]');
                if (input) { input.focus(); input.click(); return true; }
                return false;
            }""")
            
            time.sleep(0.5)
            locator_input = page.locator('input:focus')
            locator_input.press("Control+a")
            locator_input.press("Delete")
            
            for char in search_prefix:
                locator_input.type(char)
                time.sleep(0.1)
            
            print(f"Введен текст: {search_prefix}")
            
            # --- ШАГ 3: Выбор "3436" ---
            print("Ждем список (4 сек)...")
            time.sleep(4.0) 
            
            clicked = page.evaluate("""(groupNum) => {
                const allElements = document.querySelectorAll('div, span, li, a, p, td, button');
                
                for (let el of allElements) {
                    if (el.children.length === 0) {
                        const text = el.textContent.trim();
                        if (text === groupNum || text.startsWith(groupNum) || text.includes(groupNum)) {
                            const rect = el.getBoundingClientRect();
                            if (rect.width > 10 && rect.height > 10) { el.click(); return text; }
                        }
                    }
                }
                return false;
            }""", group_number)
            
            if clicked:
                print(f"✅ Выбран элемент: {clicked}")
                time.sleep(1.5)
            else:
                print("Элемент не найден, пробуем клавиатурой...")
                locator_input.press("ArrowDown")
                time.sleep(0.5)
                locator_input.press("Enter")
                time.sleep(1.0)

        except Exception as e:
            print(f"Ошибка ввода или выбора: {e}")
            browser.close()
            return

        # --- ШАГ 4: Кнопка "Расписание занятий" ---
        try:
            button_text = "Расписание занятий"
            page.evaluate("""(btnText) => {
                const buttons = document.querySelectorAll('button, input[type="submit"]');
                for (let btn of buttons) {
                    if (btn.textContent.includes(btnText) || btn.value.includes(btnText)) {
                        if (!btn.disabled) { btn.click(); return true; }
                    }
                }
                return false;
            }""", button_text)
            print("Кнопка нажата. Ждем рендеринга (5 сек)...")
            time.sleep(5.0) 
        except Exception as e:
            print(f"Ошибка на этапе кнопки: {e}")
            browser.close()
            return

        # --- ШАГ 5: СБОР И СОРТИРОВКА ДАННЫХ ---
        html_content = page.content()
        browser.close()
        
        soup = BeautifulSoup(html_content, 'html.parser')
        all_tables = soup.find_all('table')
        
        print(f"Найдено таблиц на странице: {len(all_tables)}. Начинаем обработку...")

        all_data = []
        header_row = None
        
        for i, table in enumerate(all_tables):
            # 1. Проверка структуры таблицы (наличие нужных колонок)
            headers = [h.get_text(strip=True).lower() for h in table.find_all('th')]
            has_time = any('время' in h for h in headers)
            has_discipline = any('дисциплина' in h for h in headers)
            has_type = any('вид занятия' in h for h in headers)
            
            if not (has_time and has_discipline and has_type):
                continue 
            
            # 2. Проверка наличия дат в теле таблицы
            date_found = False
            rows_to_check = table.find_all('tr')[:10]
            for row in rows_to_check:
                cells = row.find_all(['td', 'th'])
                for cell in cells:
                    text = cell.get_text(strip=True)
                    if re.search(r'\b\d{1,2}\.\d{1,2}\b', text):
                        date_found = True
                        break
                if date_found: break
            
            if not date_found:
                continue 

            # 3. ОПРЕДЕЛЕНИЕ ДНЯ НЕДЕЛИ
            # Ищем название дня в контексте над таблицей (500 символов до начала тега <table>)
            table_html = str(table)
            pos = html_content.find(table_html)
            search_context = html_content[max(0, pos-500):pos]
            
            found_day = None
            for day in days_of_week:
                if day in search_context.lower():
                    found_day = day.capitalize() # Сохраняем как "Понедельник"
                    break
            
            # Если не нашли над таблицей, проверяем саму таблицу (на всякий случай)
            if not found_day:
                table_text = table.get_text(strip=True).lower()
                for day in days_of_week:
                    if day in table_text:
                        found_day = day.capitalize()
                        break
            
            if not found_day:
                # Если день недели не найден вообще, пропускаем эту таблицу
                # print(f"⚠️ Пропущена таблица {i}: не удалось определить день недели.")
                continue

            print(f"✅ Найдена таблица: {found_day} (индекс {i}).")
            
            # Сохраняем заголовок только из первой подходящей таблицы
            if header_row is None:
                header_row = [h.get_text(strip=True) for h in table.find_all('th')]
                # Добавляем нашу новую колонку "День недели" в заголовок
                header_row.append("День недели")
                if not header_row:
                    first_row = table.find('tr')
                    if first_row:
                        header_row = [c.get_text(strip=True) for c in first_row.find_all(['td', 'th'])]
                        header_row.append("День недели")

            # Сбор строк из ЭТОЙ таблицы
            rows = table.find_all('tr')
            for row in rows:
                cols = row.find_all(['td', 'th'])
                clean_cols = [col.get_text(strip=True) for col in cols]
                
                # Пропускаем пустые строки
                if not clean_cols or all(c == '' for c in clean_cols):
                    continue
                
                # Фильтр: строка должна содержать дату (ДД.ММ)
                has_date_in_row = False
                for cell_text in clean_cols:
                    if re.search(r'\b\d{1,2}\.\d{1,2}\b', cell_text):
                        has_date_in_row = True
                        break
                
                if has_date_in_row:
                    # ВАЖНО: Добавляем день недели в конец строки данных
                    clean_cols.append(found_day)
                    all_data.append(clean_cols)

        if not all_data:
            print("❌ Не найдено ни одной строки с расписанием.")
            return

        # --- ШАГ 6: СОРТИРОВКА ПО ДНЯМ НЕДЕЛИ ---
        # Сортируем список all_data по значению в последней колонке (День недели)
        # Используем словарь day_order для правильного порядка (Пн, Вт, Ср...)
        try:
            all_data.sort(key=lambda x: day_order.get(x[-1], 99))
            print("✅ Данные отсортированы по дням недели.")
        except Exception as e:
            print(f"⚠️ Ошибка сортировки: {e}. Данные останутся в порядке нахождения.")

        # --- ШАГ 7: ЗАПИСЬ В CSV ---
        filename = 'schedule_sorted_week.csv'
        with open(filename, 'w', newline='', encoding='utf-8-sig') as csvfile:
            writer = csv.writer(csvfile)
            
            if header_row:
                writer.writerow(header_row)
            else:
                writer.writerow(['Время', 'Дата', 'Дисциплина', 'Вид занятия', 'Здание / Аудитория', 'День недели'])
            
            writer.writerows(all_data)
        
        print(f"✅ Успешно! Расписание сохранено в {filename}.")
        print(f"Всего строк с занятиями: {len(all_data)}")
        
        print("\n--- Пример первых 5 строк (с колонкой День недели) ---")
        for r in all_data[:5]:
            print(r)

if __name__ == "__main__":
    parse_kai_sorted_week()
