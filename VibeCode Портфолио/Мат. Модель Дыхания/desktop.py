#!/usr/bin/env python3
"""Оконная версия: python desktop.py или python app.py --desktop.

Полностью на Python/Tkinter: никаких браузеров, JS и pip-пакетов.
"""
from __future__ import annotations

import csv
import math
from pathlib import Path
import sys

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox
except ImportError:
    sys.exit("Для оконной версии нужен Tkinter.\n"
             "На Ubuntu/Debian: sudo apt install python3-tk\n"
             "Либо используйте браузерную версию: python app.py")

from model import Simulation, validate_oxygen
from svg_canvas import SVGScene

BG = "#f5f7f3"
INK = "#1e3c34"
MUTED = "#85958a"
LINE = "#e3e9e3"
GREEN = "#285c48"
ROOT = Path(__file__).resolve().parent


def number(value: float, digits: int = 1) -> str:
    return f"{value:,.{digits}f}".replace(",", "\u00a0").replace(".", ",")


def short(value: float) -> str:
    return number(value, 0 if value == int(value) else 1)


class DesktopApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.sim = Simulation()
        self.scene = SVGScene(ROOT / "interface.html")
        self.alive = True
        self.timer = None
        root.title("Дыхание человека — интерактивная модель")
        root.geometry("1250x860")
        root.minsize(1040, 740)
        root.configure(bg=BG)
        root.option_add("*Font", ("Segoe UI", 10))
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.oxygen = tk.StringVar(value="21")
        self.error = tk.StringVar(value="")
        self.values = {}
        self._build()
        self.oxygen.trace_add("write", self.input_changed)
        self.root.bind("<space>", self.space)
        self.entry.bind("<Return>", lambda event: self.toggle())
        self.input_changed()
        self.tick()

    @staticmethod
    def label(parent, text="", fg=INK, bg=None, size=10, weight="normal", **kw):
        return tk.Label(parent, text=text, fg=fg,
                        bg=bg or parent.cget("bg"), font=("Segoe UI", size, weight), **kw)

    @staticmethod
    def button(parent, text, command, primary=False, **kw):
        return tk.Button(parent, text=text, command=command, relief="flat", bd=0,
                         bg=GREEN if primary else "#f0f5ee",
                         fg="white" if primary else "#68866f",
                         activebackground="#204c3c" if primary else "#e5eee2",
                         activeforeground="white" if primary else GREEN,
                         disabledforeground="#9eb4a2", cursor="hand2", padx=15, pady=11,
                         font=("Segoe UI", 10), **kw)

    def _build(self):
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=28, pady=(21, 15))
        mark = tk.Label(header, text="O₂", bg=GREEN, fg="#d0e5cf",
                        font=("Segoe UI", 16, "bold"), padx=9, pady=3)
        mark.pack(side="left")
        self.label(header, "дыхание / lab", size=16, weight="bold").pack(side="left", padx=10)
        self.label(header, "PYTHON / TKINTER   ·   УЧЕБНАЯ МОДЕЛЬ", fg="#94a696", size=9).pack(side="right")
        intro = tk.Frame(self.root, bg=BG)
        intro.pack(fill="x", padx=28, pady=(7, 18))
        self.label(intro, "Дыхание человека.", size=25).pack(anchor="w")
        self.label(intro, "Проследите путь кислорода — от первого вдоха до клеток организма.",
                   fg=MUTED, size=10).pack(anchor="w", pady=(4, 0))

        controls = tk.Frame(self.root, bg="white", highlightbackground=LINE, highlightthickness=1)
        controls.pack(fill="x", padx=28, pady=(0, 17))
        text = tk.Frame(controls, bg="white")
        text.pack(side="left", padx=21, pady=18)
        self.label(text, "Кислород в воздухе", size=11, weight="bold").pack(anchor="w")
        self.label(text, "Введите процент от 0 до 100", fg=MUTED, size=9).pack(anchor="w", pady=(5, 0))
        entry_frame = tk.Frame(controls, bg="#f9fbf8", highlightbackground="#cfdcd2", highlightthickness=1)
        entry_frame.pack(side="left", padx=14, pady=15)
        self.entry = tk.Entry(entry_frame, textvariable=self.oxygen, width=5, font=("Segoe UI", 20),
                              fg=INK, bg="#f9fbf8", disabledbackground="#f9fbf8", disabledforeground=MUTED,
                              relief="flat", borderwidth=0, insertbackground=GREEN)
        self.entry.pack(side="left", padx=(12, 1), pady=6)
        self.label(entry_frame, "%", fg="#9aae9e", size=16).pack(side="left", padx=(0, 12))
        presets = tk.Frame(controls, bg="white")
        presets.pack(side="left", padx=4)
        self.label(presets, "Быстрый выбор", size=8, fg=MUTED).pack(anchor="w", pady=(0, 5))
        row = tk.Frame(presets, bg="white"); row.pack()
        self.presets = []
        for value in (15, 21, 30):
            b = tk.Button(row, text=f"{value}%", command=lambda n=value: self.oxygen.set(str(n)),
                          relief="flat", bd=0, bg="#f1f6ee", fg="#698871", padx=8, pady=4,
                          font=("Segoe UI", 8), activebackground="#e2eddf", cursor="hand2")
            b.pack(side="left", padx=(0, 5)); self.presets.append(b)
        actions = tk.Frame(controls, bg="white")
        actions.pack(side="right", padx=20)
        self.reset_button = self.button(actions, "↺  Сбросить", self.reset)
        self.reset_button.pack(side="right", padx=(8, 0))
        self.run_button = self.button(actions, "▶  Начать дыхание", self.toggle, primary=True, width=21)
        self.run_button.pack(side="right")
        self.error_label = tk.Label(self.root, textvariable=self.error, fg="#b55d48", bg=BG,
                                    font=("Segoe UI", 9), anchor="w")

        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=28)
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)
        scene_frame = tk.Frame(body, bg="white", highlightbackground=LINE, highlightthickness=1)
        scene_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 17))
        scene_header = tk.Frame(scene_frame, bg="white")
        scene_header.pack(fill="x", padx=21, pady=(16, 4))
        self.label(scene_header, "01—03   От воздуха к клеткам", size=10, weight="bold").pack(side="left")
        self.status_label = self.label(scene_header, "Ожидание запуска", fg=MUTED, size=9)
        self.status_label.pack(side="right")
        self.canvas = tk.Canvas(scene_frame, bg="white", bd=0, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=5)
        self.label(scene_frame, "● Кислород O₂       ● Другие газы       ● Эритроциты       ● Обратный кровоток",
                   size=8, fg="#8ca496").pack(pady=(0, 10))
        footer = tk.Frame(scene_frame, bg="#fafcf8", highlightbackground=LINE, highlightthickness=1)
        footer.pack(fill="x")
        for column, (key, title, default) in enumerate([
            ("phase", "Фаза дыхания", "Ожидание"),
            ("volume", "Объём вдоха", "0 мл"),
            ("cycles", "Полных циклов", "0"),
            ("elapsed", "Время опыта", "00:00"),
        ]):
            footer.grid_columnconfigure(column, weight=1)
            cell = tk.Frame(footer, bg="#fafcf8")
            cell.grid(row=0, column=column, sticky="w", padx=19, pady=13)
            self.label(cell, title, fg="#96a298", size=8).pack(anchor="w")
            self.values[key] = self.label(cell, default, fg="#637967", size=12)
            self.values[key].pack(anchor="w", pady=(4, 0))
        self.progress = tk.Canvas(scene_frame, bg="#eef3ed", height=3, bd=0, highlightthickness=0)
        self.progress.pack(fill="x")

        stats = tk.Frame(body, bg=BG, width=286)
        stats.grid(row=0, column=1, sticky="nsew")
        stats.grid_propagate(False)
        stats.grid_columnconfigure(0, weight=1)
        for i in range(3): stats.grid_rowconfigure(i, weight=1)
        for i, (key, title, description, colour) in enumerate([
            ("inspired", "Поступило в лёгкие", "Весь кислород, вдохнутый за опыт", "#44aaa1"),
            ("blood", "Перешло в кровь", "Через альвеолы · 20% от вдохнутого", "#de856c"),
            ("tissues", "Доставлено тканям", "Перенос кровью · задержка 3 секунды", "#b99c58"),
        ]):
            card = tk.Frame(stats, bg="white", highlightbackground=LINE, highlightthickness=1)
            card.grid(row=i, column=0, sticky="nsew", pady=(0, 11))
            self.label(card, f"●   {title}", fg=colour, size=10).pack(anchor="w", padx=18, pady=(17, 5))
            value_row = tk.Frame(card, bg="white"); value_row.pack(anchor="w", padx=18)
            self.values[key] = self.label(value_row, "0,0", size=27)
            self.values[key].pack(side="left")
            self.label(value_row, "мл O₂", size=9, fg="#a0b0a3").pack(side="left", padx=7, pady=(12, 0))
            self.label(card, description, size=8, fg="#9aa89d").pack(anchor="w", padx=18, pady=(4, 16))
        balance = tk.Frame(stats, bg=GREEN)
        balance.grid(row=3, column=0, sticky="ew")
        self.label(balance, "Расчёт на один вдох", fg="#d6e8d9", size=10).pack(anchor="w", padx=18, pady=(18, 12))
        self.values["forecast"] = self.label(balance, "500 мл воздуха  →  105 мл O₂", fg="#e2eee5", size=10)
        self.values["forecast"].pack(anchor="w", padx=18)
        self.values["forecast_blood"] = self.label(balance, "Из них в кровь: 21 мл O₂", fg="#b8d1bf", size=9)
        self.values["forecast_blood"].pack(anchor="w", padx=18, pady=(8, 6))
        self.label(balance, "Условный коэффициент 20%", fg="#99bca4", size=8).pack(anchor="w", padx=18, pady=(0, 17))

        bottom = tk.Frame(self.root, bg=BG)
        bottom.pack(fill="x", padx=28, pady=(13, 9))
        self.label(bottom, "12 циклов / мин   ·   Вдох 2 с / выдох 3 с   ·   Все показатели суммарные, в мл O₂",
                   fg="#94a697", size=8).pack(side="left")
        self.save_button = tk.Button(bottom, text="Сохранить CSV", command=self.save,
                                     bg=BG, fg="#6c967b", relief="flat", bd=0, font=("Segoe UI", 9), cursor="hand2")
        self.save_button.pack(side="right")
        self.info_button = tk.Button(bottom, text="Формулы и допущения", command=self.explain,
                                     bg=BG, fg="#6c967b", relief="flat", bd=0, font=("Segoe UI", 9), cursor="hand2")
        self.info_button.pack(side="right", padx=20)
        foot = tk.Frame(self.root, bg=BG); foot.pack(fill="x", padx=28, pady=(4, 19))
        self.label(foot, "Учебная визуализация. Не предназначена для медицинских расчётов.",
                   fg="#a1afa4", size=8).pack(side="left")
        self.label(foot, "Пробел — начать / пауза / продолжить", fg="#a1afa4", size=8).pack(side="right")

    def input_changed(self, *args):
        self.error.set("")
        try:
            oxygen = validate_oxygen(self.oxygen.get())
        except ValueError:
            return
        self.values["forecast"].configure(text=f"500 мл воздуха  →  {short(5*oxygen)} мл O₂")
        self.values["forecast_blood"].configure(text=f"Из них в кровь: {short(oxygen)} мл O₂")
        for value,b in zip((15,21,30),self.presets):
            b.configure(bg="#e0ecde" if oxygen==value else "#f1f6ee")

    def controls(self):
        idle=self.sim.status=="idle"; running=self.sim.status=="running"
        self.entry.configure(state="normal" if idle else "disabled")
        for b in self.presets: b.configure(state="normal" if idle else "disabled")
        self.run_button.configure(text="▶  Начать дыхание" if idle else "Ⅱ  Приостановить" if running else "▶  Продолжить")
        self.reset_button.configure(state="disabled" if idle else "normal")
        self.save_button.configure(state="normal" if self.sim.elapsed()>0 else "disabled")
        self.status_label.configure(text="Ожидание запуска" if idle else "Опыт идёт" if running else "На паузе",
                                    fg=MUTED if idle else "#50825d" if running else "#a18e61")

    def toggle(self):
        try:
            if self.sim.status=="idle": self.sim.start(self.oxygen.get())
            elif self.sim.status=="running": self.sim.pause()
            else: self.sim.resume()
        except ValueError as error:
            self.error.set(str(error))
            messagebox.showwarning("Проверьте концентрацию кислорода", str(error), parent=self.root)
            self.entry.focus_set()
        self.controls()

    def reset(self):
        self.sim.reset(); self.error.set(""); self.controls(); self.entry.focus_set()

    def space(self, event):
        # У кнопок собственная обработка пробела: не вызывать команду дважды.
        if not isinstance(self.root.focus_get(), (tk.Entry, tk.Button, tk.Text)):
            self.toggle()
            return "break"

    def tick(self):
        if not self.alive: return
        state=self.sim.snapshot()
        self.controls()
        for key in ("inspired","blood","tissues"):
            text=number(state[key+"_total_ml"])
            self.values[key].configure(text=text,font=("Segoe UI",27 if len(text)<9 else 21))
        self.values["phase"].configure(text="Ожидание" if state["status"]=="idle" else "↓  Вдох" if state["phase"]=="inhale" else "↑  Выдох")
        self.values["volume"].configure(text=number(state["air_volume_ml"],0)+" мл")
        self.values["cycles"].configure(text=str(state["completed_breaths"]))
        seconds=int(state["elapsed_s"])
        elapsed=(f"{seconds//3600:02}:" if seconds>=3600 else "")+f"{seconds//60%60:02}:{seconds%60:02}"
        self.values["elapsed"].configure(text=elapsed)
        self.scene.draw(self.canvas,state)
        self.progress.delete("all")
        if state["status"]!="idle":
            width=self.progress.winfo_width()*(state["elapsed_s"]%5)/5
            self.progress.create_rectangle(0,0,width,3,fill="#82bdab",outline="")
        self.timer=self.root.after(33,self.tick)

    def save(self):
        if self.sim.elapsed()<=0: return
        destination=filedialog.asksaveasfilename(parent=self.root,title="Сохранить результаты опыта",
                defaultextension=".csv",initialfile="respiration.csv",filetypes=[("CSV-таблица","*.csv")])
        if not destination: return
        try:
            with open(destination,"w",encoding="utf-8-sig",newline="") as f:
                csv.writer(f,delimiter=";").writerows(self.sim.report_rows())
        except OSError as error:
            messagebox.showerror("Не удалось сохранить файл",str(error),parent=self.root)

    def explain(self):
        messagebox.showinfo("Формулы и допущения", "Это упрощённая учебная модель.\n\n"
            "Дыхательный объём одного вдоха: 500 мл.\n"
            "Частота: 12 циклов/мин. Вдох 2 с, выдох 3 с.\n"
            "Объём изменяется плавно, по полукосинусоиде.\n\n"
            "F = введённый процент кислорода / 100\n"
            "I(t) = F × суммарный вдохнутый воздух\n"
            "B(t) = 0,20 × I(t − 0,6 с)\n"
            "T(t) = B(t − 3 с)\n\n"
            "I — поступило в лёгкие; B — перешло в кровь;\n"
            "T — доставлено клеткам организма. Всё в мл O₂.\n"
            "Показатели накопленные, а не текущий запас O₂.\n\n"
            "20% и задержки заданы условно для демонстрации.\n"
            "Оставшиеся 80% O₂ условно выводятся с выдохом.\n"
            "Цвета и размеры условные: венозная кровь не синяя.\n"
            "Не моделируются SpO₂, CO₂, остаточный объём лёгких,\n"
            "парциальные давления и клеточный метаболизм.\n"
            "Нельзя использовать для медицинских расчётов\n"
            "или оценки безопасности дыхательных смесей.",parent=self.root)

    def close(self):
        self.alive=False
        if self.timer is not None: self.root.after_cancel(self.timer)
        self.root.destroy()


def main():
    try:
        root=tk.Tk()
    except tk.TclError as error:
        sys.exit(f"Не удалось открыть графическое окно: {error}\n"
                 "В среде без дисплея используйте python app.py --no-browser")
    try:
        DesktopApp(root)
        root.mainloop()
    except (OSError, ValueError) as error:
        messagebox.showerror("Не удалось загрузить модель",str(error),parent=root)
        root.destroy()


if __name__=="__main__":
    main()
