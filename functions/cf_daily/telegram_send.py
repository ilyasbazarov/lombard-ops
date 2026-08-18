"""
functions/cf_daily/telegram_send.py — T-1-0, шаг 3

Отправка ОДНОГО сообщения в Telegram Bot API — тот же вызов, что предъявлен
`reference/T-0-18_telegram_contour_setup_2026-08-18.md` (шаг 5: `message_id`,
`date`, `chat.id`, `chat.type` в ответе `sendMessage`).

**Решение исполнителя (зафиксировано в артефакте):** используется стандартная
библиотека (`urllib.request`), не пакет `requests` — вызов один, без сессий и
ретраев (`05 §II` «Ограничения» брифа: одна отправка, один вызов, отказ — стоп
и лог, идемпотентность — предмет `T-1-4`), лишняя зависимость на холодном
старте Cloud Function не оправдана.

Токен и `chat_id` — параметры функции, читаются из хранилища секретов СНАРУЖИ, в
`main.py`: этот модуль секретов не читает сам — проверяется тестом (сплошной
поиск клиента хранилища секретов в этом файле даёт 0 совпадений, шаг 3 брифа T-1-0).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

TELEGRAM_API_BASE = "https://api.telegram.org"


class TelegramSendError(RuntimeError):
    """Отправка сообщения не удалась — ответ API не `ok: true` либо транспортный отказ."""


def _default_http_post(url: str, data: bytes) -> dict:
    request = urllib.request.Request(
        url, data=data, method="POST", headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read()
    except urllib.error.URLError as exc:
        raise TelegramSendError(f"транспортный отказ Telegram API: {exc}") from exc
    return json.loads(body)


def send_message(
    token_value: str,
    chat_id: str,
    text: str,
    *,
    http_post: Callable[[str, bytes], dict] = _default_http_post,
) -> str:
    """`POST /bot<token_value>/sendMessage`. Возвращает `message_id` из ответа.

    Отказ (не `ok: true`, либо транспортная ошибка) поднимает `TelegramSendError` —
    тихого проглатывания нет (`05 §II`, «gate'ы блокирующие, не warning»)."""
    url = f"{TELEGRAM_API_BASE}/bot{token_value}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
    response: dict[str, Any] = http_post(url, payload)
    if not response.get("ok"):
        raise TelegramSendError(f"Telegram API отказ: {response}")
    message_id = response["result"]["message_id"]
    return str(message_id)
