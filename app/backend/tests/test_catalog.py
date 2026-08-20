"""app-lombard · tests/test_catalog.py — шаг 7 брифа T-2-4: локально проверяемые сценарии
GET /api/catalog, БЕЗ деплоя и без обращения к реальному BigQuery.

`bigquery_client.fetch_vehicle_catalog` подменяется (monkeypatch) заготовленными строками —
проверяется middleware (401 без токена) и сериализация эндпоинта, а не сеть/GCP.

Запуск: PYTHONPATH=app/backend python3 -m pytest app/backend/tests/test_catalog.py -v -s
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import auth as auth_module  # noqa: E402
import main  # noqa: E402


def _fake_decoded(role, uid):
    return {"uid": uid, "role": role}


_FAKE_ROWS = [
    {
        "make": "Toyota", "model": "Camry 70", "liquidity_class": "green",
        "ltv_max": 0.75, "buyout_price": 18000.0, "price_source": "synthetic",
        "comment": "test fixture", "updated_at": "2026-08-20T00:00:00+00:00",
    },
    {
        "make": "Land Rover", "model": "Range Rover", "liquidity_class": "red",
        "ltv_max": None, "buyout_price": None, "price_source": "synthetic",
        "comment": "стоп-класс", "updated_at": "2026-08-20T00:00:00+00:00",
    },
]


def test_catalog_no_token_returns_401():
    client = main.app.test_client()
    resp = client.get("/api/catalog")
    print("REQ: GET /api/catalog  (без заголовка Authorization)")
    print("RESP:", resp.status_code, resp.get_json())
    assert resp.status_code == 401
    assert resp.get_json()["reason"] == "missing_token"


def test_catalog_any_role_returns_200_with_rows(monkeypatch):
    """Матрица ролей 12_UX_CONTRACT.md §4: /catalog — просмотр всеми тремя ролями. Проверяем
    произвольную роль (assessor), т.к. эндпоинт НЕ несёт require_role."""
    monkeypatch.setattr(auth_module, "verify_id_token", lambda t: _fake_decoded("assessor", "assessor-test-1"))
    monkeypatch.setattr(main, "fetch_vehicle_catalog", lambda: _FAKE_ROWS)
    client = main.app.test_client()
    resp = client.get("/api/catalog", headers={"Authorization": "Bearer fake-assessor-token"})
    print("REQ: GET /api/catalog  (Authorization: Bearer <role=assessor>)")
    print("RESP:", resp.status_code, resp.get_json())
    assert resp.status_code == 200
    body = resp.get_json()
    assert body == _FAKE_ROWS


def test_catalog_owner_role_also_returns_200(monkeypatch):
    monkeypatch.setattr(auth_module, "verify_id_token", lambda t: _fake_decoded("owner", "owner-test-1"))
    monkeypatch.setattr(main, "fetch_vehicle_catalog", lambda: _FAKE_ROWS)
    client = main.app.test_client()
    resp = client.get("/api/catalog", headers={"Authorization": "Bearer fake-owner-token"})
    print("REQ: GET /api/catalog  (Authorization: Bearer <role=owner>)")
    print("RESP:", resp.status_code, resp.get_json())
    assert resp.status_code == 200
