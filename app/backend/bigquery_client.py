"""app-lombard · bigquery_client.py — тонкая обёртка над google.cloud.bigquery.Client (бриф T-2-4).

Единственная точка создания BigQuery-клиента для backend'а. `PROJECT_ID` берётся из окружения
(`PROJECT_ID`), при отсутствии — из значения `11_INFRA_FACTS.md` раздел «GCP»
(`project-c451b48a-07ae-4de4-961`). Явный SQL, без autodetect схемы на чтении (`05 §II`).
"""
import os

from google.cloud import bigquery

DEFAULT_PROJECT_ID = "project-c451b48a-07ae-4de4-961"
DATASET = "lombard_ops"

_client = None


def _project_id():
    return os.environ.get("PROJECT_ID", DEFAULT_PROJECT_ID)


def get_client():
    """Ленивая инициализация — реальный вызов к BigQuery только когда действительно нужен."""
    global _client
    if _client is None:
        _client = bigquery.Client(project=_project_id())
    return _client


def fetch_vehicle_catalog(client=None):
    """SELECT из vehicle_catalog, явный список колонок (02 §2), без autodetect."""
    bq = client or get_client()
    query = """
        SELECT make, model, liquidity_class, ltv_max, buyout_price, price_source, comment, updated_at
        FROM `{project}.{dataset}.vehicle_catalog`
        ORDER BY make, model
    """.format(project=_project_id(), dataset=DATASET)
    rows = bq.query(query).result()
    result = []
    for row in rows:
        result.append({
            "make": row["make"],
            "model": row["model"],
            "liquidity_class": row["liquidity_class"],
            "ltv_max": float(row["ltv_max"]) if row["ltv_max"] is not None else None,
            "buyout_price": float(row["buyout_price"]) if row["buyout_price"] is not None else None,
            "price_source": row["price_source"],
            "comment": row["comment"],
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] is not None else None,
        })
    return result
