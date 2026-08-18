"""
functions/cf_daily/test_telegram_send.py — T-1-0, шаг 3

Тест отправки в Telegram на мокнутом HTTP-вызове (без сети) плюс проверка
брифа: сплошной поиск `secretmanager` в `telegram_send.py` даёт 0 совпадений
(модуль не читает секреты сам). Запуск:
`python3 -m functions.cf_daily.test_telegram_send` из корня репозитория.
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any

from functions.cf_daily.telegram_send import TelegramSendError, send_message

_checks: list[tuple[str, Any]] = []


def check(name: str):
    def deco(fn):
        _checks.append((name, fn))
        return fn

    return deco


@check("1: send_message — успешный ответ Bot API возвращает message_id строкой")
def _t1_success():
    captured: dict[str, Any] = {}

    def fake_http_post(url: str, data: bytes) -> dict:
        captured["url"] = url
        captured["payload"] = json.loads(data.decode("utf-8"))
        return {
            "ok": True,
            "result": {
                "message_id": 13,
                "date": 1000000001,
                "chat": {"id": -1000000001, "type": "group"},
            },
        }

    message_id = send_message(
        "FAKE_TOKEN", "-1000000001", "Договор 1001: статус 🟢", http_post=fake_http_post
    )
    assert message_id == "13", f"ожидался message_id '13', получено {message_id!r}"
    assert captured["url"] == "https://api.telegram.org/botFAKE_TOKEN/sendMessage"
    assert captured["payload"]["chat_id"] == "-1000000001"
    assert captured["payload"]["text"] == "Договор 1001: статус 🟢"


@check("2: send_message — Bot API отвечает ok:false -> TelegramSendError, не тихий проход")
def _t2_api_failure():
    def fake_http_post(url: str, data: bytes) -> dict:
        return {"ok": False, "error_code": 400, "description": "chat not found"}

    try:
        send_message("FAKE_TOKEN", "0", "текст", http_post=fake_http_post)
        raise AssertionError("отказ Bot API обязан поднять TelegramSendError, а прошёл")
    except TelegramSendError as exc:
        assert "chat not found" in str(exc)


@check("3: модуль telegram_send.py не читает секреты сам — 0 совпадений 'secretmanager'")
def _t3_no_secretmanager_import():
    source = Path(__file__).with_name("telegram_send.py").read_text(encoding="utf-8")
    assert "secretmanager" not in source, (
        "telegram_send.py обязан принимать токен параметром, не читать Secret Manager сам "
        "(шаг 3 брифа T-1-0)"
    )


def main() -> int:
    failed = 0
    for name, fn in _checks:
        try:
            fn()
        except Exception:  # noqa: BLE001
            failed += 1
            print(f"[ПРОВАЛЕНО] {name}")
            traceback.print_exc()
        else:
            print(f"[пройдено]  {name}")
    print(f"\nвсего проверок: {len(_checks)}; провалено {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
