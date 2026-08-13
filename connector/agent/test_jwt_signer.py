"""
connector/agent/test_jwt_signer.py — T-0-8, шаг 5-Б п.2 (ПОПРАВКА 3, `ADR-050`)

Тест модуля подписи JWT (`jwt_signer.py`), по тому же принципу, что
`test_access_point.py`: реестр проверок `check`/`_checks`, каждая либо ничего не
бросает (успех), либо кидает `AssertionError` (печатается как провал), вердикт —
«провалено N», не код возврата (`05 §I`).

Пара ключей — тестовая, генерируется ЭТИМ файлом в памяти и пишется во временный
файл только на время теста; к серверу ERP и к платформе (`sts.googleapis.com`) тест
не обращается — структура JWT проверяется ЛОКАЛЬНО (`decode_unverified_header_and_claims`
+ независимая проверка подписи объектом публичного ключа тестовой пары), не через
внешний сервис. Отрицательный случай (истёкший `exp`) — тоже локальная проверка
структуры, отдельная от положительной (`ADR-033`: проба обязана различать исходы).

Запуск: `python3 -m connector.agent.test_jwt_signer` из корня репозитория.
"""

from __future__ import annotations

import base64
import json
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Any

from connector.agent.jwt_signer import (
    DEFAULT_TTL_SECONDS,
    MAX_TTL_SECONDS,
    JwtSignerError,
    JwtSigningConfig,
    build_claims,
    decode_unverified_header_and_claims,
    is_expired,
    sign_jwt,
    write_credential_source_file,
)

_checks: list[tuple[str, Any]] = []


def check(name: str):
    def deco(fn):
        _checks.append((name, fn))
        return fn

    return deco


# ---------------------------------------------------------------------------
# Тестовая пара ключей — сгенерирована этим файлом, не путь на сервере клиента.
# ---------------------------------------------------------------------------


def _generate_test_keypair() -> tuple[bytes, Any]:
    """Возвращает (PEM приватного ключа, объект публичного ключа `cryptography`)."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pem, private_key.public_key()


def _write_temp_key(pem: bytes, tmp_dir: Path) -> Path:
    path = tmp_dir / "test_private_key.pem"
    path.write_bytes(pem)
    return path


def _make_config(tmp_dir: Path, *, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> tuple[JwtSigningConfig, Any]:
    pem, public_key = _generate_test_keypair()
    key_path = _write_temp_key(pem, tmp_dir)
    cfg = JwtSigningConfig(
        issuer="https://issuer.example.invalid/test",
        subject="lombard-agent-test",
        audience="//iam.googleapis.com/projects/000/locations/global/"
        "workloadIdentityPools/test-pool/providers/test-provider",
        private_key_path=key_path,
        kid="test-kid-1",
        ttl_seconds=ttl_seconds,
    )
    return cfg, public_key


def _verify_signature_locally(jwt_compact: str, public_key: Any) -> None:
    """Независимая проверка подписи ПУБЛИЧНЫМ ключом тестовой пары — доказывает, что
    подпись действительно над `header.claims` и действительно тем приватным ключом,
    который был на диске, а не заглушка."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    header_b64, claims_b64, sig_b64 = jwt_compact.split(".")
    signing_input = f"{header_b64}.{claims_b64}".encode("ascii")
    signature = base64.urlsafe_b64decode(sig_b64 + "=" * (-len(sig_b64) % 4))
    public_key.verify(signature, signing_input, padding.PKCS1v15(), hashes.SHA256())
    # verify() бросает InvalidSignature при несовпадении — исключение здесь
    # намеренно не глушится, проброс наверх и есть провал проверки.
    _ = InvalidSignature  # заглушка, чтобы импорт не выглядел неиспользуемым


@check("1: подпись валидна — независимая проверка публичным ключом тестовой пары проходит")
def _t1_signature_valid():
    with tempfile.TemporaryDirectory() as td:
        cfg, public_key = _make_config(Path(td))
        jwt_compact = sign_jwt(cfg, now=1_700_000_000)
        _verify_signature_locally(jwt_compact, public_key)


@check("2: структура заголовка — alg=RS256, typ=JWT, kid совпадает с конфигом")
def _t2_header_structure():
    with tempfile.TemporaryDirectory() as td:
        cfg, _ = _make_config(Path(td))
        jwt_compact = sign_jwt(cfg, now=1_700_000_000)
        header, _claims = decode_unverified_header_and_claims(jwt_compact)
        assert header["alg"] == "RS256", header
        assert header["typ"] == "JWT", header
        assert header["kid"] == cfg.kid, header


@check("3: структура claims — iss/sub/aud совпадают с конфигом, iat/exp расставлены по TTL")
def _t3_claims_structure():
    with tempfile.TemporaryDirectory() as td:
        cfg, _ = _make_config(Path(td), ttl_seconds=600)
        now = 1_700_000_000
        jwt_compact = sign_jwt(cfg, now=now)
        _header, claims = decode_unverified_header_and_claims(jwt_compact)
        assert claims["iss"] == cfg.issuer, claims
        assert claims["sub"] == cfg.subject, claims
        assert claims["aud"] == cfg.audience, claims
        assert claims["iat"] == now, claims
        assert claims["exp"] == now + 600, claims


@check("4: build_claims самостоятельно (без подписи) даёт те же поля, что и claims из токена")
def _t4_build_claims_matches_token():
    with tempfile.TemporaryDirectory() as td:
        cfg, _ = _make_config(Path(td))
        now = 1_700_000_000
        expected = build_claims(cfg, now=now)
        jwt_compact = sign_jwt(cfg, now=now)
        _header, claims = decode_unverified_header_and_claims(jwt_compact)
        assert claims == expected, (claims, expected)


@check("5: exp-iat не больше 24 часов — конфиг с TTL сверх потолка отбивается ДО подписи")
def _t5_ttl_ceiling_rejected():
    with tempfile.TemporaryDirectory() as td:
        pem, _ = _generate_test_keypair()
        key_path = _write_temp_key(pem, Path(td))
        try:
            JwtSigningConfig(
                issuer="https://issuer.example.invalid/test",
                subject="lombard-agent-test",
                audience="//iam.googleapis.com/projects/000/...",
                private_key_path=key_path,
                kid="test-kid-1",
                ttl_seconds=MAX_TTL_SECONDS + 1,
            )
        except JwtSignerError:
            pass
        else:
            raise AssertionError("TTL сверх 24 часов обязан отбиваться JwtSignerError")


@check("6: пустые issuer/subject/audience — CONTEXT GAP отбивается ДО подписи, значение не подставляется")
def _t6_empty_required_fields_rejected():
    with tempfile.TemporaryDirectory() as td:
        pem, _ = _generate_test_keypair()
        key_path = _write_temp_key(pem, Path(td))
        for field in ("issuer", "subject", "audience"):
            kwargs = dict(
                issuer="https://issuer.example.invalid/test",
                subject="lombard-agent-test",
                audience="//iam.googleapis.com/projects/000/...",
                private_key_path=key_path,
                kid="test-kid-1",
            )
            kwargs[field] = ""
            try:
                JwtSigningConfig(**kwargs)
            except JwtSignerError:
                pass
            else:
                raise AssertionError(f"пустой {field} обязан отбиваться JwtSignerError")


@check(
    "7-НЕГАТИВ: истёкший exp — структура токена показывает is_expired()=True "
    "ДО отправки на STS (отдельная проверка отрицательного случая, ADR-033)"
)
def _t7_expired_structure_detected():
    with tempfile.TemporaryDirectory() as td:
        cfg, _ = _make_config(Path(td), ttl_seconds=60)
        issued_at = 1_700_000_000
        jwt_compact = sign_jwt(cfg, now=issued_at)
        _header, claims = decode_unverified_header_and_claims(jwt_compact)
        # Момент проверки — ПОСЛЕ истечения (issued_at + ttl + запас).
        check_time = issued_at + 60 + 1
        assert is_expired(claims, now=check_time) is True, claims
        # Положительный контроль в ТОМ ЖЕ тесте (ADR-033: проба обязана различать
        # исходы) — тот же токен, момент проверки ДО истечения, обязан дать False.
        assert is_expired(claims, now=issued_at) is False, claims


@check("8: файл приватного ключа не найден — JwtSignerError без содержимого ключа в сообщении")
def _t8_missing_key_file():
    with tempfile.TemporaryDirectory() as td:
        cfg = JwtSigningConfig(
            issuer="https://issuer.example.invalid/test",
            subject="lombard-agent-test",
            audience="//iam.googleapis.com/projects/000/...",
            private_key_path=Path(td) / "does_not_exist.pem",
            kid="test-kid-1",
        )
        try:
            sign_jwt(cfg, now=1_700_000_000)
        except JwtSignerError as exc:
            assert "does_not_exist.pem" in str(exc)
            assert "-----BEGIN" not in str(exc), "сообщение не обязано нести содержимое ключа"
        else:
            raise AssertionError("отсутствующий файл ключа обязан отбиваться JwtSignerError")


@check("9: write_credential_source_file кладёт РОВНО токен в целевой файл (без JSON-обёртки)")
def _t9_write_credential_source_file():
    with tempfile.TemporaryDirectory() as td:
        cfg, public_key = _make_config(Path(td))
        output_path = Path(td) / "credential_source.jwt"
        written = write_credential_source_file(cfg, output_path, now=1_700_000_000)
        assert written == output_path
        content = output_path.read_text(encoding="ascii")
        assert content.count(".") == 2, "ожидался JWT (header.claims.signature), а не JSON-обёртка"
        try:
            json.loads(content)
        except json.JSONDecodeError:
            pass
        else:
            raise AssertionError("содержимое не обязано быть валидным JSON целиком — это сырой JWT")
        _verify_signature_locally(content, public_key)


def main() -> int:
    failed = 0
    for name, fn in _checks:
        try:
            fn()
        except Exception:  # noqa: BLE001 — тест обязан печатать провал, не падать молча
            failed += 1
            print(f"[ПРОВАЛЕНО] {name}")
            traceback.print_exc()
        else:
            print(f"[пройдено]  {name}")
    print(f"\nвсего проверок: {len(_checks)}; провалено {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
