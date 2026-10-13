#!/usr/bin/env python3
"""Запуск: python app.py. Никаких pip-зависимостей.

Расчёты — model.py (Python), интерфейс и отрисовка — interface.html.
Каждая вкладка браузера получает отдельный опыт.
"""
from __future__ import annotations

import argparse
import csv
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import threading
import time
from urllib.parse import parse_qs, urlsplit
import uuid
import webbrowser

from model import Simulation

ROOT = Path(__file__).resolve().parent
SESSIONS: dict[str, Simulation] = {}
SESSION_LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    server_version = "Respiration/1.0"

    def send(self, body: bytes | str, content_type: str, status: int = 200,
             headers: dict | None = None) -> None:
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def json_response(self, value: dict, status: int = 200) -> None:
        self.send(json.dumps(value, ensure_ascii=False, allow_nan=False),
                  "application/json; charset=utf-8", status)

    def get_session(self, token: object) -> Simulation:
        if not isinstance(token, str):
            raise ValueError("Сессия не найдена. Обновите страницу.")
        with SESSION_LOCK:
            model = SESSIONS.get(token)
        if model is None:
            raise ValueError("Сессия не найдена. Обновите страницу.")
        return model

    def do_GET(self) -> None:
        url = urlsplit(self.path)
        query = parse_qs(url.query)
        if url.path in ("/", "/index.html", "/interface.html"):
            try:
                self.send((ROOT / "interface.html").read_bytes(),
                          "text/html; charset=utf-8")
            except OSError:
                self.json_response({"error": "Не найден interface.html рядом с app.py."}, 500)
        elif url.path == "/favicon.ico":
            self.send(b"", "image/x-icon", 204)
        elif url.path == "/api/health":
            self.json_response({"ok": True, "engine": "Python"})
        elif url.path in ("/api/state", "/api/report.csv"):
            try:
                sim = self.get_session(query.get("session", [None])[0])
                if url.path == "/api/state":
                    self.json_response(sim.snapshot())
                else:
                    text = io.StringIO(newline="")
                    csv.writer(text, delimiter=";").writerows(sim.report_rows())
                    self.send(b"\xef\xbb\xbf" + text.getvalue().encode("utf-8"),
                              "text/csv; charset=utf-8", headers={
                                  "Content-Disposition": 'attachment; filename="respiration.csv"'
                              })
            except ValueError as error:
                self.json_response({"error": str(error)}, 400)
        else:
            self.json_response({"error": "Страница не найдена."}, 404)

    def do_POST(self) -> None:
        route = urlsplit(self.path).path
        if route not in {"/api/session", "/api/start", "/api/pause",
                         "/api/resume", "/api/reset"}:
            self.json_response({"error": "Команда не найдена."}, 404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 <= length <= 4096:
                self.json_response({"error": "Слишком большой запрос."}, 413)
                return
            try:
                data = json.loads(self.rfile.read(length) or b"{}")
            except (json.JSONDecodeError, UnicodeDecodeError):
                raise ValueError("Некорректный JSON.") from None
            if not isinstance(data, dict):
                raise ValueError("Ожидался объект JSON.")
            if route == "/api/session":
                with SESSION_LOCK:
                    now = time.monotonic()
                    expired = [key for key, model in SESSIONS.items()
                               if now - model.last_access > 3600]
                    for key in expired:
                        del SESSIONS[key]
                    if len(SESSIONS) >= 256:
                        self.json_response({"error": "Слишком много открытых опытов."}, 503)
                        return
                    token = uuid.uuid4().hex
                    sim = Simulation()
                    SESSIONS[token] = sim
                self.json_response({"session": token, "state": sim.snapshot()})
                return
            sim = self.get_session(data.get("session"))
            if route == "/api/start":
                state = sim.start(data.get("oxygen_percent"))
            elif route == "/api/pause":
                state = sim.pause()
            elif route == "/api/resume":
                state = sim.resume()
            else:
                state = sim.reset()
            self.json_response(state)
        except (ValueError, TypeError) as error:
            self.json_response({"error": str(error)}, 400)

    def log_message(self, format: str, *args) -> None:
        # Не засорять консоль опросом счётчиков.
        if not self.path.startswith("/api/state"):
            super().log_message(format, *args)


def main() -> None:
    parser = argparse.ArgumentParser(description="Интерактивная модель дыхания человека")
    parser.add_argument("--host", default="127.0.0.1", help="Адрес сервера")
    parser.add_argument("--port", type=int, default=8000, help="Порт (по умолчанию 8000)")
    parser.add_argument("--no-browser", action="store_true", help="Не открывать браузер")
    parser.add_argument("--desktop", action="store_true", help="Открыть Python/Tkinter, без браузера")
    args = parser.parse_args()
    if args.desktop:
        from desktop import main as desktop_main
        desktop_main()
        return
    try:
        server = ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError as error:
        parser.exit(1, f"Не удалось открыть порт {args.port}: {error}\n"
                       "Попробуйте: python app.py --port 8001\n")
    server.daemon_threads = True
    address = "127.0.0.1" if args.host in ("0.0.0.0", "::") else args.host
    url = f"http://{address}:{server.server_port}"
    print(f"\nМодель дыхания запущена: {url}\n"
          "Остановить сервер: Ctrl+C\n", flush=True)
    if not args.no_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nОпыт завершён.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
