#!/usr/bin/env python3
"""HTTP-сервер «Двадцятого Києва»: віддає фронтенд (../frontend) і має один ендпоінт.

    POST /api/user-point   {"user_point": [latitude, longitude]}
                           → {"result": {...} | null}  (результат logic.on_user_point)

Уся логіка — у logic.py, дані — у store.py. Потрібен лише Python 3.9+.

Запуск:  python backend/server.py   →   http://127.0.0.1:8000
"""

import json
import os
import traceback
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import logic
import store

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


def present(result):
    """Приводить відповідь logic.on_user_point до вигляду, який показує фронтенд."""
    if result is None:
        return None
    
    # Якщо прийшов список точок (наприклад, 5 штук), обробляємо кожну
    if isinstance(result, list):
        return [present(item) for item in result]
        
    if not isinstance(result, dict):
        raise TypeError("on_user_point має повертати dict, список або None")
        
    out = {}
    # У CSV назва події зберігається в полі name.
    out["title"] = str(result.get("id", result.get("name", result.get("title", "Історична подія"))))
    for key in ("date", "description", "source_url"):
        if result.get(key) is not None:
            value = result[key]
            out[key] = value.isoformat() if hasattr(value, "isoformat") else str(value)
    if result.get("coordinates") is not None:
        out["coordinates"] = result["coordinates"]
    if result.get("period") is not None:
        number = store.parse_period(result["period"])
        out["period"] = number
        out["period_name"] = store.PERIODS[number]
    return out


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)

    def _json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if urlparse(self.path).path.startswith("/api/"):
            return self._json(404, {"error": "не знайдено"})
        super().do_GET()

    def do_POST(self):
        if urlparse(self.path).path != "/api/user-point":
            return self._json(404, {"error": "не знайдено"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4096:
                raise ValueError("некоректний розмір запиту")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("очікувався JSON-об'єкт")
            if payload.get("user_point") != [None, None]:
                user_point = store.check_coordinates(payload.get("user_point"))   # [latitude, longitude]
            period = payload.get("period")
        except (ValueError, UnicodeDecodeError) as err:
            return self._json(400, {"error": str(err)})

        try:
            if payload.get("user_point") != [None, None]:
                result = present(logic.on_user_point(user_point, period))
            else:
                result = present(logic.on_period(period))
        except Exception as err:   # помилка у вашому коді з logic.py
            traceback.print_exc()
            return self._json(500, {"error": f"Помилка в logic.on_user_point: {err}"})
        self._json(200, {"result": result})


def main():
    logic.setup()
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)   # лише локально
    print(f"Сторінка та API: http://127.0.0.1:{port}  (Ctrl+C — зупинити)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nЗупинено.")


if __name__ == "__main__":
    main()
