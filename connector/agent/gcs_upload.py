"""
connector/agent/gcs_upload.py — T-0-8, шаг 4

Загрузка выгрузки в GCS с явно названным поведением при недоступности бакета
(требование шага 4 брифа `T-0-8`): повтор с задержкой, предел попыток, запись в
локальный журнал при исчерпании попыток, отсутствие тихой потери данных.

Бакет — `${PROJECT_ID}-cfsource`, имя взято из `11_INFRA_FACTS.md` / `briefs/T-0-7.md`
(создан задачей `T-0-7`), не придумано этой задачей.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("lombard.agent.gcs_upload")

DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_BASE_DELAY_SECONDS = 2.0
DEFAULT_JOURNAL_DIR = Path(__file__).with_name("upload_journal")


class UploadFailedPersisted(Exception):
    """Все попытки загрузки в GCS исчерпаны; объект сохранён в локальный журнал,
    потеря не произошла — это факт, а не тихое молчание."""

    def __init__(self, journal_path: Path, blob_name: str, attempts: int):
        self.journal_path = journal_path
        self.blob_name = blob_name
        self.attempts = attempts
        super().__init__(
            f"загрузка {blob_name} не удалась за {attempts} попыток; "
            f"объект сохранён в локальный журнал: {journal_path}"
        )


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    base_delay_seconds: float = DEFAULT_BASE_DELAY_SECONDS


def _default_gcs_client() -> Any:
    """Ленивый импорт: `google-cloud-storage` нужен на сервере агента, не в каждой
    сессии, которая читает этот модуль (тот же разрез, что у `fdb` в
    `access_point.py`).

    `project` передаётся явно из `PROJECT_ID`: федеративные учётные данные
    (`ADR-050`) — в отличие от ключа сервисного аккаунта — не несут номер проекта
    внутри себя, `storage.Client()` без аргумента не может его определить сам
    (`Project was not passed and could not be determined from the environment`,
    замер шага 7 `T-0-8`, 2026-08-17)."""
    from google.cloud import storage  # type: ignore

    return storage.Client(project=os.environ.get("PROJECT_ID"))


def upload_bytes(
    bucket_name: str,
    blob_name: str,
    data: bytes,
    *,
    policy: RetryPolicy = RetryPolicy(),
    journal_dir: Path = DEFAULT_JOURNAL_DIR,
    client_factory: Callable[[], Any] = _default_gcs_client,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """Загружает `data` в `gs://bucket_name/blob_name`.

    Поведение при недоступности GCS: до `policy.max_attempts` попыток с
    экспоненциальной задержкой (`base_delay_seconds * 2**попытка`). Все провалились
    → объект пишется в `journal_dir` (локальный журнал, не теряется молча) и
    бросается `UploadFailedPersisted` — вызывающий код узнаёт об отказе явно, а не
    по тишине.

    Возвращает `gs://...` путь при успехе.
    """
    last_error: Exception | None = None
    for attempt in range(1, policy.max_attempts + 1):
        try:
            client = client_factory()
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(blob_name)
            blob.upload_from_string(data)
            gs_path = f"gs://{bucket_name}/{blob_name}"
            logger.info(
                "загрузка удалась с попытки %d/%d: %s (%d байт)",
                attempt,
                policy.max_attempts,
                gs_path,
                len(data),
            )
            return gs_path
        except Exception as exc:  # noqa: BLE001 — любая причина недоступности GCS
            last_error = exc
            logger.warning(
                "попытка загрузки %d/%d не удалась (%s): %s",
                attempt,
                policy.max_attempts,
                blob_name,
                exc,
            )
            if attempt < policy.max_attempts:
                delay = policy.base_delay_seconds * (2 ** (attempt - 1))
                sleep(delay)

    journal_dir.mkdir(parents=True, exist_ok=True)
    journal_path = journal_dir / blob_name.replace("/", "__")
    journal_path.write_bytes(data)
    logger.error(
        "все %d попыток загрузки исчерпаны для %s (последняя ошибка: %s); "
        "объект сохранён БЕЗ ПОТЕРИ в локальный журнал: %s",
        policy.max_attempts,
        blob_name,
        last_error,
        journal_path,
    )
    raise UploadFailedPersisted(journal_path, blob_name, policy.max_attempts)


def replay_journal(
    bucket_name: str,
    *,
    journal_dir: Path = DEFAULT_JOURNAL_DIR,
    policy: RetryPolicy = RetryPolicy(),
    client_factory: Callable[[], Any] = _default_gcs_client,
    sleep: Callable[[float], None] = time.sleep,
) -> list[str]:
    """Доисполнение хвоста после восстановления связи (не-идемпотентные операции,
    `05 §I`): читает журнал, пробует дозагрузить каждый файл, при успехе удаляет
    его из журнала. Ничего не изобретает заново — блобы называются так же, как при
    первой попытке (имя файла в журнале — это `blob_name` с заменой `/` на `__`)."""
    uploaded: list[str] = []
    if not journal_dir.exists():
        return uploaded
    for path in sorted(journal_dir.iterdir()):
        if not path.is_file():
            continue
        blob_name = path.name.replace("__", "/")
        data = path.read_bytes()
        try:
            gs_path = upload_bytes(
                bucket_name,
                blob_name,
                data,
                policy=policy,
                journal_dir=journal_dir,
                client_factory=client_factory,
                sleep=sleep,
            )
        except UploadFailedPersisted:
            continue
        else:
            path.unlink()
            uploaded.append(gs_path)
    return uploaded
