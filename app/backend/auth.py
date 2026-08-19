"""app-lombard · auth.py — проверка ID-токена Identity Platform и роли из custom claims.

Роли: owner / manager / assessor (00_CHARTER.md §2). Источник роли — custom claim `role`,
проставляется скриптом T-2-1_identity_platform_setup.sh при создании тестовых пользователей
(шаг 4/5 брифа T-2-1) и, для боевых пользователей, отдельной задачей вне scope T-2-1.

`verify_id_token` — единственная точка вызова firebase_admin.auth.verify_id_token; вынесена
отдельной функцией специально, чтобы unit-тест (tests/test_auth.py) мог её подменить
(monkeypatch) и проверить 401/403 БЕЗ обращения к реальному Identity Platform — это и есть
"локально проверяемый тест" шага 2 брифа: он проверяет middleware, а не сеть.
"""
from functools import wraps

import firebase_admin
from firebase_admin import auth as firebase_auth
from flask import jsonify, request

_firebase_app = None


def _ensure_initialized():
    """Ленивая инициализация firebase_admin — только когда реально нужен вызов к Identity
    Platform (прод/деплой). Тесты (monkeypatch verify_id_token) сюда не доходят."""
    global _firebase_app
    if _firebase_app is None:
        _firebase_app = firebase_admin.initialize_app()
    return _firebase_app


def verify_id_token(id_token):
    _ensure_initialized()
    return firebase_auth.verify_id_token(id_token)


def require_auth(f):
    """401, если заголовка Authorization: Bearer <token> нет, он пуст, либо verify_id_token
    бросает исключение (просроченный/некорректный/поддельный токен)."""

    @wraps(f)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return jsonify({"error": "unauthorized", "reason": "missing_token"}), 401
        bearer_value = header[len("Bearer "):].strip()
        if not bearer_value:
            return jsonify({"error": "unauthorized", "reason": "missing_token"}), 401
        try:
            decoded = verify_id_token(bearer_value)
        except Exception:
            return jsonify({"error": "unauthorized", "reason": "invalid_token"}), 401
        request.user = decoded
        return f(*args, **kwargs)

    return wrapper


def require_role(*roles):
    """403, если custom claim `role` декодированного токена не входит в допустимый список.
    Применяется ПОСЛЕ require_auth (require_auth — внешний декоратор, require_role — внутренний,
    см. main.py)."""

    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            user = getattr(request, "user", None) or {}
            role = user.get("role")
            if role not in roles:
                return (
                    jsonify(
                        {
                            "error": "forbidden",
                            "reason": "role_mismatch",
                            "have": role,
                            "need": list(roles),
                        }
                    ),
                    403,
                )
            return f(*args, **kwargs)

        return wrapper

    return decorator
