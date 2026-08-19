"""app-lombard · tests/test_auth.py — шаг 2 брифа T-2-1: локально проверяемые отрицательные
случаи, БЕЗ деплоя и без обращения к реальному Identity Platform.

auth.verify_id_token подменяется (monkeypatch) фейковыми decoded-токенами — так проверяется
middleware (401/403), а не сеть/GCP. Реальная проверка на задеплоенном сервисе — шаг 8 брифа.

Запуск: PYTHONPATH=app/backend python3 -m pytest app/backend/tests/test_auth.py -v -s
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import auth as auth_module  # noqa: E402
import main  # noqa: E402


def _fake_decoded(role, uid):
    return {"uid": uid, "role": role}


def test_no_token_returns_401():
    client = main.app.test_client()
    resp = client.get("/api/whoami")
    print("REQ: GET /api/whoami  (без заголовка Authorization)")
    print("RESP:", resp.status_code, resp.get_json())
    assert resp.status_code == 401
    assert resp.get_json()["reason"] == "missing_token"


def test_assessor_role_on_owner_resource_returns_403(monkeypatch):
    monkeypatch.setattr(auth_module, "verify_id_token", lambda t: _fake_decoded("assessor", "assessor-test-1"))
    client = main.app.test_client()
    resp = client.get("/api/owner/only", headers={"Authorization": "Bearer fake-assessor-token"})
    print("REQ: GET /api/owner/only  (Authorization: Bearer <role=assessor>)")
    print("RESP:", resp.status_code, resp.get_json())
    assert resp.status_code == 403
    assert resp.get_json()["reason"] == "role_mismatch"


def test_owner_role_on_owner_resource_returns_200(monkeypatch):
    monkeypatch.setattr(auth_module, "verify_id_token", lambda t: _fake_decoded("owner", "owner-test-1"))
    client = main.app.test_client()
    resp = client.get("/api/owner/only", headers={"Authorization": "Bearer fake-owner-token"})
    print("REQ: GET /api/owner/only  (Authorization: Bearer <role=owner>)")
    print("RESP:", resp.status_code, resp.get_json())
    assert resp.status_code == 200


def test_invalid_token_returns_401(monkeypatch):
    def _raise(t):
        raise ValueError("invalid signature")

    monkeypatch.setattr(auth_module, "verify_id_token", _raise)
    client = main.app.test_client()
    resp = client.get("/api/whoami", headers={"Authorization": "Bearer garbage-token"})
    print("REQ: GET /api/whoami  (Authorization: Bearer <garbage>)")
    print("RESP:", resp.status_code, resp.get_json())
    assert resp.status_code == 401
    assert resp.get_json()["reason"] == "invalid_token"
