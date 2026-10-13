"""Учебная модель дыхания. Только стандартная библиотека Python.

Все объёмы кислорода указаны в миллилитрах, время — в секундах.
Это кинематическая демонстрация, а не медицинская модель.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import math
import threading
import time
from typing import Callable


@dataclass(frozen=True)
class Parameters:
    tidal_volume_ml: float = 500.0
    inhalation_s: float = 2.0
    exhalation_s: float = 3.0
    absorption_fraction: float = 0.20
    gas_exchange_delay_s: float = 0.60
    transport_delay_s: float = 3.0

    @property
    def cycle_s(self) -> float:
        return self.inhalation_s + self.exhalation_s

    @property
    def breaths_per_minute(self) -> float:
        return 60.0 / self.cycle_s


PARAMETERS = Parameters()


def validate_oxygen(value: object) -> float:
    """Принять число 0..100, в том числе десятичную запятую."""
    if isinstance(value, bool) or value is None:
        raise ValueError("Введите число от 0 до 100.")
    try:
        oxygen = float(str(value).strip().replace(",", "."))
    except (ValueError, TypeError, OverflowError):
        raise ValueError("Введите число от 0 до 100.") from None
    if not math.isfinite(oxygen) or not 0.0 <= oxygen <= 100.0:
        raise ValueError("Содержание кислорода должно быть от 0 до 100%.")
    return oxygen


def lung_expansion(elapsed: float, p: Parameters = PARAMETERS) -> float:
    """Плавное увеличение объёма на вдохе и уменьшение на выдохе."""
    phase = max(0.0, elapsed) % p.cycle_s
    if phase < p.inhalation_s:
        return 0.5 * (1.0 - math.cos(math.pi * phase / p.inhalation_s))
    return 0.5 * (1.0 + math.cos(
        math.pi * (phase - p.inhalation_s) / p.exhalation_s
    ))


def inspired_air(elapsed: float, p: Parameters = PARAMETERS) -> float:
    """Суммарный вдохнутый воздух; выдох не уменьшает накопленный счётчик."""
    if elapsed <= 0:
        return 0.0
    cycles = math.floor(elapsed / p.cycle_s)
    phase = elapsed - cycles * p.cycle_s
    partial = (
        0.5 * (1.0 - math.cos(math.pi * phase / p.inhalation_s))
        if phase < p.inhalation_s else 1.0
    )
    return (cycles + partial) * p.tidal_volume_ml


def inspired_air_rate(elapsed: float, p: Parameters = PARAMETERS) -> float:
    """Производная накопленного объёма: мл/с, только на вдохе."""
    if elapsed <= 0:
        return 0.0
    phase = elapsed % p.cycle_s
    if phase >= p.inhalation_s:
        return 0.0
    return (p.tidal_volume_ml * math.pi / (2.0 * p.inhalation_s)
            * math.sin(math.pi * phase / p.inhalation_s))


def calculate(elapsed: float, oxygen_percent: float,
              p: Parameters = PARAMETERS) -> dict:
    """Аналитический расчёт: точность не зависит от частоты кадров.

    I(t) = F · суммарный вдохнутый воздух;
    B(t) = 0.20 · I(t − 0.60);
    T(t) = B(t − 3.00).
    При t <= 0 накопление равно нулю. Между B и T нет потерь кислорода.
    """
    elapsed = max(0.0, float(elapsed))
    fraction = validate_oxygen(oxygen_percent) / 100.0
    phase_t = elapsed % p.cycle_s
    inhaling = phase_t < p.inhalation_s
    phase_duration = p.inhalation_s if inhaling else p.exhalation_s
    phase_elapsed = phase_t if inhaling else phase_t - p.inhalation_s
    expansion = lung_expansion(elapsed, p)
    inspired = inspired_air(elapsed, p) * fraction
    blood = (inspired_air(elapsed - p.gas_exchange_delay_s, p)
             * fraction * p.absorption_fraction)
    tissues = (inspired_air(elapsed - p.gas_exchange_delay_s - p.transport_delay_s, p)
               * fraction * p.absorption_fraction)
    return {
        "elapsed_s": elapsed,
        "oxygen_percent": oxygen_percent,
        "phase": "inhale" if inhaling else "exhale",
        "phase_elapsed_s": phase_elapsed,
        "phase_duration_s": phase_duration,
        "phase_remaining_s": phase_duration - phase_elapsed,
        "phase_progress": phase_elapsed / phase_duration,
        "expansion": expansion,
        "cycle_number": math.floor(elapsed / p.cycle_s) + 1,
        "completed_breaths": math.floor(elapsed / p.cycle_s),
        "air_volume_ml": expansion * p.tidal_volume_ml,
        "oxygen_in_current_volume_ml": expansion * p.tidal_volume_ml * fraction,
        "inspired_total_ml": inspired,
        "blood_total_ml": blood,
        "tissues_total_ml": tissues,
        "in_transit_ml": max(0.0, blood - tissues),
        "inspired_rate_ml_s": inspired_air_rate(elapsed, p) * fraction,
        "blood_rate_ml_s": (inspired_air_rate(elapsed - p.gas_exchange_delay_s, p)
                            * fraction * p.absorption_fraction),
        "tissues_rate_ml_s": (inspired_air_rate(elapsed - p.gas_exchange_delay_s
                                              - p.transport_delay_s, p)
                             * fraction * p.absorption_fraction),
        "oxygen_per_breath_ml": p.tidal_volume_ml * fraction,
        "blood_per_breath_ml": p.tidal_volume_ml * fraction * p.absorption_fraction,
        "parameters": {**asdict(p), "cycle_s": p.cycle_s,
                       "breaths_per_minute": p.breaths_per_minute},
    }


class Simulation:
    """Часы опыта. Пауза действительно останавливает анимацию и все счётчики."""

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self.clock = clock
        self.lock = threading.RLock()
        self.oxygen_percent = 21.0
        self.status = "idle"
        self._elapsed = 0.0
        self._started_at: float | None = None
        self.started_wall: str | None = None
        self.last_access = self.clock()

    def elapsed(self) -> float:
        with self.lock:
            if self.status == "running" and self._started_at is not None:
                return self._elapsed + max(0.0, self.clock() - self._started_at)
            return self._elapsed

    def snapshot(self) -> dict:
        with self.lock:
            self.last_access = self.clock()
            result = calculate(self.elapsed(), self.oxygen_percent)
            result.update(status=self.status, started_wall=self.started_wall)
            if self.status == "idle":
                result.update(phase="idle", cycle_number=0)
            return result

    def start(self, oxygen_percent: object) -> dict:
        with self.lock:
            if self.status != "idle":
                raise ValueError("Сначала сбросьте текущий опыт.")
            self.oxygen_percent = validate_oxygen(oxygen_percent)
            self._elapsed = 0.0
            self._started_at = self.clock()
            self.started_wall = datetime.now(timezone.utc).isoformat()
            self.status = "running"
            return self.snapshot()

    def pause(self) -> dict:
        with self.lock:
            if self.status == "running":
                self._elapsed = self.elapsed()
                self._started_at = None
                self.status = "paused"
            return self.snapshot()

    def resume(self) -> dict:
        with self.lock:
            if self.status == "paused":
                self._started_at = self.clock()
                self.status = "running"
            return self.snapshot()

    def reset(self) -> dict:
        with self.lock:
            self._elapsed = 0.0
            self._started_at = None
            self.started_wall = None
            self.status = "idle"
            return self.snapshot()

    def report_rows(self, interval: float = 0.5) -> list[list]:
        """Снимок опыта в CSV: одна строка каждые 0.5 с и конечное состояние."""
        with self.lock:
            elapsed = self.elapsed()
            oxygen = self.oxygen_percent
        interval = max(0.1, interval)
        # Ограничение размера отчёта для очень длительных опытов.
        interval = max(interval, elapsed / 100_000)
        times = [i * interval for i in range(math.floor(elapsed / interval) + 1)]
        if not math.isclose(times[-1], elapsed, abs_tol=1e-8):
            times.append(elapsed)
        rows = [["Время, с", "Кислород в воздухе, %", "Фаза",
                 "Объём вдоха, мл", "O2 поступило в лёгкие, мл",
                 "O2 поступило в кровь, мл", "O2 доставлено тканям, мл"]]
        for t in times:
            s = calculate(t, oxygen)
            values = [t, oxygen, s["air_volume_ml"], s["inspired_total_ml"],
                      s["blood_total_ml"], s["tissues_total_ml"]]
            # Десятичная запятая + разделитель ; удобны для русской версии Excel.
            formatted = [f"{v:.3f}".replace(".", ",") for v in values]
            rows.append([formatted[0], formatted[1],
                         "Вдох" if s["phase"] == "inhale" else "Выдох",
                         *formatted[2:]])
        return rows
