"""app-lombard · main.py — каркас Cloud Run сервиса (бриф T-2-1).

Отдаёт: (1) минимальный API за Identity Platform (401 без токена, 403 при несовпадении роли —
auth.py); (2) статику собранного React frontend (app/frontend) — единственный экран каркаса
/login назначен 12_UX_CONTRACT.md §3.1.

Экраны реестра/карточки/справочника/осмотра — T-2-2…T-2-5, вне scope этой задачи.
"""
import os

from flask import Flask, jsonify, request, send_from_directory

from auth import require_auth, require_role
from bigquery_client import fetch_vehicle_catalog

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "dist")

app = Flask(__name__, static_folder=None)


@app.get("/healthz")
def healthz():
    return jsonify({"status": "ok"}), 200


@app.get("/api/whoami")
@require_auth
def whoami():
    return (
        jsonify({"uid": request.user.get("uid") or request.user.get("sub"), "role": request.user.get("role")}),
        200,
    )


@app.get("/api/owner/only")
@require_auth
@require_role("owner")
def owner_only():
    """Ресурс, размеченный ролью owner — используется приёмкой 403 для роли assessor
    (шаг 2 и шаг 8-в брифа T-2-1)."""
    return jsonify({"ok": True, "resource": "owner-only"}), 200


@app.get("/api/catalog")
@require_auth
def catalog():
    """Справочник ликвидности (T-2-4, 12_UX_CONTRACT.md §3.6) — все три роли видят, только просмотр,
    поэтому require_role не применяется (12 §4: /catalog — просмотр owner/manager/assessor)."""
    return jsonify(fetch_vehicle_catalog()), 200


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def frontend(path):
    if path and os.path.exists(os.path.join(STATIC_DIR, path)):
        return send_from_directory(STATIC_DIR, path)
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return send_from_directory(STATIC_DIR, "index.html")
    return jsonify({"error": "frontend_not_built"}), 404


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
