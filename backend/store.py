"""Дані «Двадцятого Києва»: сховище точок, перевірка даних, межі Києва.

Публічні функції:
    add_point(id, date, period, description, coordinates)  — додати/оновити точку
    clear_point(id)                                        — видалити точку
    get_points()                                           — усі точки
    is_in_kyiv(latitude, longitude)                        — чи всередині меж Києва

Їх викликає ваш код у logic.py. Фронтенд до цих функцій доступу не має.
"""

import json
import math
import os
import re
import tempfile
import threading
from datetime import date as Date, datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
OUTLINE_FILE = BASE_DIR / "kyiv_outline.txt"
POINTS_FILE = BASE_DIR / "points.json"

YEAR_MIN, YEAR_MAX = 1917, 1991
PERIODS = {
    1: "Українська революція",
    2: "Міжвоєнний період",
    3: "Друга світова війна",
    4: "Повоєнна відбудова",
    5: "Відлига",
    6: "Застій",
    7: "Перебудова",
}


# ---------- Кордони Києва ----------

def _load_rings():
    """Читає kyiv_outline.txt: пари [довгота, широта], контури замкнені (перша точка = остання).
    Перший контур — зовнішня межа міста, решта — «дірки»."""
    text = OUTLINE_FILE.read_text(encoding="utf-8")
    pairs = re.findall(r"\[\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\]", text)
    rings, ring = [], []
    for lng, lat in pairs:
        point = (float(lng), float(lat))
        ring.append(point)
        if len(ring) > 3 and point == ring[0]:
            rings.append(ring)
            ring = []
    if ring or not rings:
        raise RuntimeError(f"{OUTLINE_FILE.name}: не вдалося розібрати контури")
    return rings


KYIV_RINGS = _load_rings()


def _ring_contains(ring, lng, lat):
    inside = False
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[i - 1]
        if (yi > lat) != (yj > lat) and lng < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
    return inside


def is_in_kyiv(latitude, longitude):
    """True, якщо точка всередині меж Києва (і не в «дірці» контуру)."""
    if not _ring_contains(KYIV_RINGS[0], longitude, latitude):
        return False
    return not any(_ring_contains(r, longitude, latitude) for r in KYIV_RINGS[1:])


# ---------- Перевірка вхідних даних ----------

def _parse_id(value):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError("Назва має бути рядком або числом")
    value = str(value).strip()
    return value


def _parse_date(value):
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, str):
        try:
            value = Date.fromisoformat(value.strip())
        except ValueError:
            raise ValueError("date має бути у форматі РРРР-ММ-ДД") from None
    if not isinstance(value, Date):
        raise ValueError("date має бути датою або рядком РРРР-ММ-ДД")
    if not YEAR_MIN <= value.year <= YEAR_MAX:
        raise ValueError(f"date: рік має бути від {YEAR_MIN} до {YEAR_MAX}")
    return value.isoformat()


def _parse_period(value):
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            value = int(text)
        else:
            for number, name in PERIODS.items():
                if name.lower() == text.lower():
                    return number
            raise ValueError(f"невідома епоха: {value!r}")
    if isinstance(value, int) and not isinstance(value, bool) and value in PERIODS:
        return value
    raise ValueError("period має бути числом від 1 до 7 або назвою епохи")


def check_coordinates(value):
    """Перевіряє [latitude, longitude]: числа, діапазон, усередині Києва. Повертає [lat, lng]."""
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError("очікувався список [latitude, longitude]")
    for number in value:
        if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number):
            raise ValueError("координати мають бути скінченними числами")
    latitude, longitude = float(value[0]), float(value[1])
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("координати поза допустимим діапазоном")
    if not is_in_kyiv(latitude, longitude):
        raise ValueError("точка поза межами Києва")
    return [latitude, longitude]


# ---------- Сховище (JSON-файл) ----------

_lock = threading.RLock()


def _read_points():
    if not POINTS_FILE.exists():
        return {}
    data = json.loads(POINTS_FILE.read_text(encoding="utf-8"))
    return {p["id"]: p for p in data}


def _write_points(points):
    # Запис через тимчасовий файл, щоб не пошкодити points.json при збої
    fd, tmp_name = tempfile.mkstemp(dir=BASE_DIR, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as tmp:
        json.dump(list(points.values()), tmp, ensure_ascii=False, indent=2)
    os.replace(tmp_name, POINTS_FILE)

# ---------- Публічні функції ----------

def add_point(name, date, period, description, coordinates, source_url=""):
    """Додає точку (або оновлює, якщо точка з таким id вже є) і повертає її.

    name        — рядок або число, унікальний ідентифікатор
    date        — "РРРР-ММ-ДД" або datetime.date, рік 1917–1991
    period      — номер епохи 1–7 або її назва (див. PERIODS)
    description — текстовий опис
    coordinates — [latitude, longitude], усередині меж Києва

    Викидає ValueError, якщо дані некоректні.
    """
    if not isinstance(description, str):
        raise ValueError("description має бути рядком")
    description = description.strip()
    if len(description) > 1000:
        raise ValueError("description: не більше 1000 символів")

    point = {
        "id": _parse_id(name),
        "date": _parse_date(date),
        "period": _parse_period(period),
        "description": description,
        "coordinates": check_coordinates(coordinates),
        "source_url": str(source_url).strip(),
    }
    with _lock:
        points = _read_points()
        points[point["id"]] = point
        _write_points(points)
    return point



def clear_point(id):
    """Видаляє точку за id. Повертає True, якщо точка існувала."""
    point_id = _parse_id(id)
    with _lock:
        points = _read_points()
        if point_id not in points:
            return False
        del points[point_id]
        _write_points(points)
    return True


def get_points():
    """Список усіх точок."""
    with _lock:
        return list(_read_points().values())

def get_points_period(period):
    """Список усіх точок конкретного періоду."""
    l = []
    with _lock:
        return [value for value in _read_points().values() if str(value["period"]) == period]


# Публічна назва для перевірки епохи (використовує server.py)
parse_period = _parse_period
