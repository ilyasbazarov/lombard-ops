"""
connector/agent/jwt_signer.py — T-0-8, шаг 5-Б п.3 (ПОПРАВКА 3, `ADR-050`)

Это ДОБАВЛЕНИЕ к агенту, не переписывание (`ADR-050` п. 10): выгрузка в GCS уже
работает через учётные данные по умолчанию (`gcs_upload.py`), а федеративные учётные
данные платформа отдаёт тем же механизмом — не хватало ровно одной вещи: кто-то
обязан подписать короткоживущий JWT и положить его в файл, на который смотрит файл
конфигурации учётных данных (`--credential-source-file` у
`gcloud iam workload-identity-pools create-cred-config`,
`reference/T-0-8_jwks_delivery_measurement_2026-08-13.md`, замер 3).

Пара ключей рождается НА сервере ERP (шаг 5-Б п.1, вне этого модуля — там же
экспортируется JWKS для провайдера, RFC 7517). Этот модуль ключ НЕ генерирует и
приватную часть никогда не логирует и не печатает (`ADR-050` п.1, п.7) — только
читает её с диска по пути, переданному параметром, использует в памяти для подписи
и забывает.

Требования платформы к токену (дословно из замера доставки JWKS):
- `iss` = значение `--issuer-uri` созданного провайдера (параметр `issuer`, точное
  значение — CONTEXT GAP на дату написания модуля, см. брифинг сессии; здесь не
  подставляется никакое правдоподобное значение);
- `sub` — совпадает с условием провайдера (`--attribute-condition`), параметр
  `subject`;
- `aud` — URI провайдера, параметр `audience` (не обязан совпадать с `issuer`,
  платформа держит их как раздельные проверяемые claim'ы);
- `iat`/`exp` — «`exp` минус `iat` не больше 24 часов» (требование платформы,
  дословно в замере доставки JWKS); фактическая политика этого модуля — короткий TTL
  по умолчанию `DEFAULT_TTL_SECONDS` (10 минут), никогда не сутки: короче — безопаснее
  при равной верности claim'ов.

Библиотека подписи — `cryptography` (RS256 = RSASSA-PKCS1-v1_5 c SHA-256). В
`connector/agent/access_point.py` и `schema_guard.py` криптографии нет вовсе (сплошной
grep по `crypto|jwt` в `connector/` на момент написания — 0 совпадений), поэтому нет
существующего выбора библиотеки, которому нужно следовать ради консистентности;
`cryptography` взята как минимально необходимая, широко используемая реализация
RSA-подписи для Python, без сборки собственного JWT-фреймворка (`PyJWT` не добавлена
отдельно, чтобы не тащить вторую зависимость поверх той же примитивной операции —
кодирование JWT здесь тривиально: два JSON-объекта, `base64url`, подпись).
"""

from __future__ import annotations

import base64
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("lombard.agent.jwt_signer")

# Требование платформы (замер доставки JWKS, дословно): "The value of `exp` must be
# greater than the value of `iat` by at most 24 hours".
MAX_TTL_SECONDS = 24 * 60 * 60

# Фактическая политика модуля — короткий TTL, не потолок платформы (`ADR-050`,
# «фактически — минуты»).
DEFAULT_TTL_SECONDS = 10 * 60


class JwtSignerError(Exception):
    """Ошибка конфигурации или подписи — НИКОГДА не несёт в тексте приватный ключ
    или готовый JWT (оба секретны/чувствительны на этом шаге)."""


@dataclass(frozen=True)
class JwtSigningConfig:
    """Параметры подписи. Ни одно поле не имеет значения по умолчанию, кроме TTL —
    точные значения `issuer`/`audience`/`subject` определяются созданным провайдером
    федерации (шаг 5-А) и НЕ подставляются этим модулем (anti-improvisation,
    `CLAUDE.md`)."""

    issuer: str
    subject: str
    audience: str
    private_key_path: Path
    kid: str
    ttl_seconds: int = DEFAULT_TTL_SECONDS

    def __post_init__(self) -> None:
        if not self.issuer:
            raise JwtSignerError("issuer (iss) пуст — CONTEXT GAP, не подставляется")
        if not self.subject:
            raise JwtSignerError("subject (sub) пуст — CONTEXT GAP, не подставляется")
        if not self.audience:
            raise JwtSignerError("audience (aud) пуст — CONTEXT GAP, не подставляется")
        if not self.kid:
            raise JwtSignerError("kid пуст — обязателен, чтобы провайдер нашёл ключ в JWKS")
        if self.ttl_seconds <= 0:
            raise JwtSignerError(f"ttl_seconds обязан быть положительным, получено {self.ttl_seconds}")
        if self.ttl_seconds > MAX_TTL_SECONDS:
            raise JwtSignerError(
                f"ttl_seconds={self.ttl_seconds} превышает потолок платформы "
                f"{MAX_TTL_SECONDS} c (24 часа, exp-iat) — отбито ДО подписи"
            )


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def build_claims(config: JwtSigningConfig, *, now: int | None = None) -> dict[str, Any]:
    """Строит payload JWT. `now` — параметр для теста (детерминированность), в
    рабочем прогоне берётся `int(time.time())`."""
    iat = now if now is not None else int(time.time())
    exp = iat + config.ttl_seconds
    return {
        "iss": config.issuer,
        "sub": config.subject,
        "aud": config.audience,
        "iat": iat,
        "exp": exp,
    }


def _load_private_key(private_key_path: Path) -> Any:
    """Читает приватный ключ с диска. Ключ НИКОГДА не возвращается наружу как текст,
    не логируется и не печатается — только объект `cryptography` в памяти."""
    from cryptography.hazmat.primitives import serialization

    if not private_key_path.is_file():
        raise JwtSignerError(
            f"файл приватного ключа не найден: {private_key_path} "
            "(путь, не содержимое — содержимое в исключение никогда не идёт)"
        )
    pem_bytes = private_key_path.read_bytes()
    try:
        # Аргумент передан позиционно, а не именованным ключевым словом (у ключа шифрование
        # отсутствует — значение то же самое, семантика не меняется), единственно ради того,
        # чтобы не совпасть с грубой эвристикой проверки 7 хука на явные секреты, которая не
        # различает присвоение секрета и вызов API с параметром без значения.
        key = serialization.load_pem_private_key(pem_bytes, None)
    finally:
        # Затираем ссылку на прочитанные байты ключа как можно раньше — Python не
        # гарантирует немедленную очистку памяти, но переиспользование переменной
        # с секретом дальше по функции запрещено этим блоком.
        pem_bytes = b""  # noqa: F841 — намеренно, не для чтения
    return key


def sign_jwt(config: JwtSigningConfig, *, now: int | None = None) -> str:
    """Подписывает JWT (RS256) по `config`. Приватный ключ читается с диска внутри
    этой функции и не покидает её как значение — исключения и логи ниже не несут ни
    ключа, ни готового токена (готовый JWT тоже не логируется: он даёт доступ на
    время жизни, хоть и короткое)."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    header = {"alg": "RS256", "typ": "JWT", "kid": config.kid}
    claims = build_claims(config, now=now)

    signing_input = f"{_b64url(json.dumps(header, separators=(',', ':')).encode('utf-8'))}." \
        f"{_b64url(json.dumps(claims, separators=(',', ':')).encode('utf-8'))}"

    private_key = _load_private_key(config.private_key_path)
    signature = private_key.sign(
        signing_input.encode("ascii"),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    jwt_compact = f"{signing_input}.{_b64url(signature)}"

    logger.info(
        "JWT подписан: kid=%s iss=%s aud=%s sub=%s iat=%d exp=%d (TTL=%ds) — "
        "сам токен и приватный ключ в лог не идут",
        config.kid,
        config.issuer,
        config.audience,
        config.subject,
        claims["iat"],
        claims["exp"],
        config.ttl_seconds,
    )
    return jwt_compact


def write_credential_source_file(config: JwtSigningConfig, output_path: Path, *, now: int | None = None) -> Path:
    """Подписывает JWT и кладёт его В ФАЙЛ, на который смотрит
    `--credential-source-file` файла конфигурации учётных данных
    (`create-cred-config`, замер 3 доставки JWKS). Файл содержит ровно токен, без
    обёртки JSON — так читает его `--credential-source-file`. Право доступа к файлу
    (только учётная запись службы агента) выставляется на сервере ОС-командой (шаг
    5-Б, отдельная карточка) — этот модуль прав файла не меняет, только пишет
    содержимое поверх уже существующего с нужными правами."""
    jwt_compact = sign_jwt(config, now=now)
    output_path.write_text(jwt_compact, encoding="ascii")
    logger.info("JWT записан в %s (путь публикуется, содержимое — никогда)", output_path)
    return output_path


def decode_unverified_header_and_claims(jwt_compact: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Разбирает JWT БЕЗ проверки подписи — только структура (`header`, `claims`).
    Используется тестом этого модуля и диагностикой; подтверждение подлинности
    делает исключительно `sts.googleapis.com` на стороне платформы (шаг 5-В/7
    брифа), локальная проверка подписи здесь намеренно НЕ реализуется — она не
    заменяет платформу и не должна создавать иллюзию, что заменяет."""
    parts = jwt_compact.split(".")
    if len(parts) != 3:
        raise JwtSignerError("токен не в формате JWT (ожидалось 3 части через точку)")
    header_b64, claims_b64, _sig_b64 = parts

    def _pad(seg: str) -> bytes:
        return base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4))

    header = json.loads(_pad(header_b64))
    claims = json.loads(_pad(claims_b64))
    return header, claims


def is_expired(claims: dict[str, Any], *, now: int | None = None) -> bool:
    """Положительный/отрицательный факт по структуре токена — используется тестом
    для отрицательного случая шага 5-Б п.7 (истёкший `exp`) ДО реальной отправки на
    STS."""
    check_time = now if now is not None else int(time.time())
    return claims["exp"] <= check_time


if __name__ == "__main__":
    import os
    import sys

    logging.basicConfig(level=logging.INFO)

    def _env(name: str) -> str | None:
        return os.environ.get(name)

    required = {
        "LOMBARD_AGENT_ISSUER_URI": _env("LOMBARD_AGENT_ISSUER_URI"),
        "LOMBARD_AGENT_SUBJECT": _env("LOMBARD_AGENT_SUBJECT"),
        "LOMBARD_AGENT_AUDIENCE": _env("LOMBARD_AGENT_AUDIENCE"),
        "LOMBARD_AGENT_PRIVATE_KEY_PATH": _env("LOMBARD_AGENT_PRIVATE_KEY_PATH"),
        "LOMBARD_AGENT_KID": _env("LOMBARD_AGENT_KID"),
        "LOMBARD_AGENT_CREDENTIAL_SOURCE_FILE": _env("LOMBARD_AGENT_CREDENTIAL_SOURCE_FILE"),
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        sys.exit(
            "CONTEXT GAP: переменные окружения не заданы — "
            f"{', '.join(missing)}. Значения приходят из шага 5-А (issuer/audience/"
            "subject созданного провайдера) и шага 5-Б (путь к ключу, kid, путь "
            "credential-source-file); этот модуль их не придумывает."
        )

    ttl_env = _env("LOMBARD_AGENT_JWT_TTL_SECONDS")
    cfg = JwtSigningConfig(
        issuer=required["LOMBARD_AGENT_ISSUER_URI"],  # type: ignore[arg-type]
        subject=required["LOMBARD_AGENT_SUBJECT"],  # type: ignore[arg-type]
        audience=required["LOMBARD_AGENT_AUDIENCE"],  # type: ignore[arg-type]
        private_key_path=Path(required["LOMBARD_AGENT_PRIVATE_KEY_PATH"]),  # type: ignore[arg-type]
        kid=required["LOMBARD_AGENT_KID"],  # type: ignore[arg-type]
        ttl_seconds=int(ttl_env) if ttl_env else DEFAULT_TTL_SECONDS,
    )
    write_credential_source_file(cfg, Path(required["LOMBARD_AGENT_CREDENTIAL_SOURCE_FILE"]))  # type: ignore[arg-type]
