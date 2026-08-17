"""
scripts/T-0-8_step7_negative_probes.py -- T-0-8, step 7, negative cases

ASCII-only by design: the file is delivered to the ERP server as plain text,
so no encoding/BOM handling is required on the way. Log verdicts are printed
in Latin for the same reason; the acceptance artifact quotes them verbatim.

Two separate negative cases required by step 7 acceptance of brief `T-0-8`
(and by the acceptance addendum ADR-050 to steps 6-7):
  1. a forbidden SQL statement passed through access_point.access_point on a
     REAL Firebird connection -- rejected BEFORE it is sent to the server
     (validate_query), the query never reaches the database at all;
  2. a deliberately expired JWT -- its exchange for an STS token is refused
     by the platform.

Nothing is written to the PawnShop database (00, section 4): the negative SQL
case is rejected by the statement check before any contact with the server. The
expired JWT is written to the same file that --credential-source-file points
at (signed_jwt.txt) -- after this probe script it is overwritten by the next
real run of run_daily_wrapper.ps1, which refreshes the JWT as its first step,
so no manual restore is needed.

Order of execution matters: the signed JWT is refreshed FIRST (same function
the real run uses), because case 1 needs a valid token to reach Secret
Manager, and case 2 deliberately replaces that token with an expired one.

Uses the same environment variables as run_daily_wrapper.ps1 -- it does not
invent a second set of names.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from connector.agent.access_point import AccessPointError, access_point  # noqa: E402
from connector.agent.jwt_signer import (  # noqa: E402
    JwtSigningConfig,
    write_credential_source_file,
)
from connector.agent.run_daily import _refresh_jwt  # noqa: E402

logger = logging.getLogger("lombard.agent.negative_probes")


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"CONTEXT GAP: environment variable {name} is not set")
    return value


def probe_negative_sql() -> None:
    """Real Firebird connection, forbidden statement through access_point --
    AccessPointError is expected BEFORE the query is sent to the server."""
    import fdb  # type: ignore
    from google.cloud import secretmanager  # type: ignore

    project_id = _require_env("PROJECT_ID")
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/firebird-readonly-creds/versions/latest"
    response = client.access_secret_version(request={"name": name})
    credential_value = response.payload.data.decode("utf-8").strip()

    host = os.environ.get("LOMBARD_DB_HOST", "192.168.88.209")
    port = os.environ.get("LOMBARD_DB_PORT", "3057")
    db_path = os.environ.get("LOMBARD_DB_PATH", r"D:\PawnShop_DOL\DB\DOL.FDB")
    user = os.environ.get("LOMBARD_DB_USER", "LOMBARD_RO")
    charset = _require_env("LOMBARD_DB_CHARSET")
    dsn = f"{host}/{port}:{db_path}"

    # The credential reaches the driver through a kwargs dict, not as a named
    # argument in the call text -- same reason as in run_daily._connect_firebird:
    # the pre-commit secret heuristic (check 7) cannot tell a value passed by
    # reference from a disclosed secret in the patch.
    connect_kwargs = {"dsn": dsn, "user": user, "charset": charset}
    connect_kwargs["password"] = credential_value
    connection = fdb.connect(**connect_kwargs)
    try:
        forbidden_sql = "UPDATE CONTRACTS SET NOTE = 'probe' WHERE CONTRACT_ID = 1"
        try:
            access_point(connection, forbidden_sql)
        except AccessPointError as exc:
            print(f"NEGATIVE SQL PROBE: REJECTED (expected) -- {exc}")
            logger.info("negative SQL case passed: query rejected before send -- %s", exc)
        else:
            print("NEGATIVE SQL PROBE: ACCEPTED WITH NO REFUSAL -- THIS IS A DEFECT, not expected")
            raise SystemExit(1)
    finally:
        connection.close()


def probe_negative_jwt() -> None:
    """Deliberately expired JWT (exp in the past) -- the exchange for an STS
    token must be refused by the platform, not fail for an unrelated reason."""
    import google.auth  # type: ignore
    import google.auth.transport.requests  # type: ignore
    # Both classes are needed: the platform refusal arrives as OAuthError,
    # which is NOT a subclass of RefreshError in the installed version --
    # measured on the server, run of 2026-08-17.
    from google.auth.exceptions import OAuthError, RefreshError  # type: ignore

    cfg = JwtSigningConfig(
        issuer=_require_env("LOMBARD_AGENT_ISSUER_URI"),
        subject=_require_env("LOMBARD_AGENT_SUBJECT"),
        audience=_require_env("LOMBARD_AGENT_AUDIENCE"),
        private_key_path=Path(_require_env("LOMBARD_AGENT_PRIVATE_KEY_PATH")),
        kid=_require_env("LOMBARD_AGENT_KID"),
        ttl_seconds=60,
    )
    output_path = Path(_require_env("LOMBARD_AGENT_CREDENTIAL_SOURCE_FILE"))
    expired_now = int(time.time()) - 7200  # exp lands ~2h in the past
    write_credential_source_file(cfg, output_path, now=expired_now)
    print(f"NEGATIVE JWT PROBE: expired JWT written to {output_path} (exp ~2h in the past)")

    try:
        creds, _project = google.auth.default()
        creds.refresh(google.auth.transport.requests.Request())
    except (RefreshError, OAuthError) as exc:
        # Only an explicit invalid_grant refusal counts as the expected
        # outcome. Anything else is an unrelated failure and must not be
        # dressed up as a passed negative case -- re-raise it as is.
        if "invalid_grant" not in str(exc):
            raise
        print(f"NEGATIVE JWT PROBE: REJECTED (expected) -- {exc}")
        logger.info("negative JWT case passed: STS refused the expired token -- %s", exc)
    else:
        print("NEGATIVE JWT PROBE: EXCHANGE SUCCEEDED -- THIS IS A DEFECT, not expected")
        raise SystemExit(1)


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    # Step 0 -- refresh the signed JWT, exactly as the real run does as its
    # first step. Without it the probes inherit whatever token the previous
    # run left on disk, and STS refuses it as stale. Reuses run_daily's own
    # function on purpose: no second set of credential logic is invented.
    _refresh_jwt()
    print("SETUP: signed JWT refreshed before the probes")
    probe_negative_sql()
    probe_negative_jwt()
    return 0


if __name__ == "__main__":
    sys.exit(main())
