"""Логіка пошуку найближчих історичних точок для кліку на мапі."""

import csv
import math
from pathlib import Path
import hashlib
import threading
import store

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
POINTS_FILE = Path(__file__).resolve().parent / "points.json"
HASHES_FILE = Path(__file__).resolve().parent / "hashes.json"
BUF_SIZE = 65536

def _parse_csv_row(line):
    """Розбирає рядок із комою або крапкою з комою як роздільником.

    Деякі рядки у вихідних CSV мають неекрановані коми в описі,
    тому текст опису збирається з усіх проміжних колонок.
    """
    candidates = []
    for delimiter in (",", ";", "\t"):
        try:
            fields = next(csv.reader([line], delimiter=delimiter))
            if len(fields) >= 7:
                candidates.append(fields)
        except csv.Error:
            pass
    if not candidates:
        return None
    fields = max(candidates, key=len)
    if fields[0].strip().lower() == "name":
        return None
    return {
        "name": fields[0].strip(),
        "date": fields[1].strip(),
        "period": fields[2].strip(),
        "description": ",".join(fields[3:-3]).strip(),
        "latitude": fields[-3].strip(),
        "longitude": fields[-2].strip(),
        "link": fields[-1].strip(),
    }


def _normalize_date(value):
    """Перетворює дату або місяць із CSV на дату YYYY-MM-DD."""
    value = value.strip()
    if len(value) == 4 and value.isdigit():
        return value + "-01-01"
    if len(value) == 7 and value[4] == "-":
        return value + "-01"
    # У частині рядків трапляється YYYY-DD-MM замість YYYY-MM-DD.
    parts = value.split("-")
    if len(parts) == 3 and parts[1].isdigit() and int(parts[1]) > 12:
        return parts[0] + "-" + parts[2] + "-" + parts[1]
    return value


def setup():
    """Імпортує всі CSV із каталогу data/ у сховище точок."""
    if not DATA_DIR.exists():
        print(f"Каталог із CSV не знайдено: {DATA_DIR}")
        return

    imported = 0
    skipped = 0
    if not POINTS_FILE.exists():
        print("Імпортуємо з data/*.csv...")
        for csv_path in sorted(DATA_DIR.glob("*.csv")):
            try:
                with csv_path.open("r", encoding="utf-8") as file:
                    file.seek(0)
                    for line in file:
                        row = _parse_csv_row(line)
                        if row is None:
                            continue
                        try:
                            store.add_point(
                                name=row["name"],
                                date=_normalize_date(row["date"]),
                                period=row["period"],
                                description=row["description"],
                                coordinates=[float(row["latitude"]), float(row["longitude"])],
                                source_url=row["link"]
                            )
                            imported += 1
                        except (KeyError, TypeError, ValueError) as e:
                            skipped += 1
                            print(f"Не вдалося імпортувати точку \"{row["name"]}\": {e}")
            except (OSError, UnicodeError, csv.Error) as error:
                print(f"Помилка читання \"{csv_path.name}\": {error}")
        print(f"Імпорт завершено: {imported} рядків; пропущено: {skipped}; унікальних точок: {len(store.get_points())}.")
    else:
        print(f"Файл points.json вже існує - імпортувати точки не потрібно. \nУнікальних точок: {len(store.get_points())}")

    imported_hashes = 0
    skipped_hashes = 0
    if not HASHES_FILE.exists():    # create hashes.json file
        print("Імпортуємо хеш-значення з data/*.csv...")
        for csv_path in sorted(DATA_DIR.glob("*.csv")):
            try:
                with csv_path.open("r", encoding="utf-8") as file:
                    try:
                        _lock = threading.RLock()
                        file.seek(0)
                        md5 = hashlib.md5()
                        while True:
                            data = file.read(BUF_SIZE)
                            if not data:
                                break
                            md5.update(data.encode("utf-8"))
                    except Exception as e:
                        print(f"Не вдалося створити хеш-значення \"{csv_path.name}\": {e}")
                        skipped_hashes += 1

                    try:
                        file.seek(0)
                        reader = csv.reader(file)
                        header = next(reader)
                        row1 = next(reader)
                        with _lock:
                            hashes = store.read_hashes()
                            period = int(row1[2])
                            hashes[period] = {"period": period, "hash": md5.hexdigest()}
                            store.write_hashes({key: value for key, value in sorted(hashes.items(), key=lambda item: item[0])})
                            imported_hashes += 1
                    except Exception as e:
                        print(f"Не вдалося додати хеш-значення \"{csv_path.name}\" до hashes.json: {e}")
                        skipped_hashes += 1
            except (OSError, UnicodeError, csv.Error) as error:
                print(f"Помилка читання \"{csv_path.name}\": {error}")
        print(f"Імпорт завершено: {imported_hashes} рядків; пропущено: {skipped_hashes}; унікальних точок: {len(store.read_hashes())}.")
    else:   # check every data/*.csv file for the same hash value
        print(f"Файл hashes.json вже існує - імпортувати хеш-значення не потрібно. \nУнікальних хеш-значень: {len(store.read_hashes())}")
    


def distance_m(a, b):
    """Відстань між двома [широта, довгота] у метрах (формула гаверсинуса)."""
    lat1, lng1, lat2, lng2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def nearest_points(user_point, period, limit=7):
    """Повертає до limit найближчих імпортованих точок до кліку користувача."""
    points = store.get_points_period(period)
    points.sort(key=lambda point: distance_m(user_point, point["coordinates"]))
    return points[:limit]


def on_user_point(user_point, period):
    """Повертає п'ять найближчих подій до [latitude, longitude]."""
    return nearest_points(user_point, period)

def on_period(period):
    return store.get_points_period(period)