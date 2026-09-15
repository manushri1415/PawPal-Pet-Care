"""Secrets from SSM Parameter Store, loaded once when a Lambda starts.

The deployment never puts a secret value in its template, its environment
variables or the frontend bundle. The function is told parameter *names*
(``PAWPAL_OWNER_KEY_PARAMETER=/pawpal/prod/owner-key`` and so on), reads the
SecureString values with its own IAM role at cold start, and places them in
the process environment under the names the app already reads
(``PAWPAL_OWNER_KEY``, ``ANTHROPIC_API_KEY``, ``PAWPAL_ORIGIN_VERIFY_SECRET``).

Every failure fails closed: a parameter that cannot be read leaves its
variable unset, which means no owner space (503), no Claude (the free model),
or -- for the origin secret -- every request refused (api/origin.py).
Parameter names are logged; values never are.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

_log = logging.getLogger("pawpal.secrets")

# Environment variable the app reads -> variable naming its SSM parameter.
SECRET_PARAMETERS = {
    "PAWPAL_OWNER_KEY": "PAWPAL_OWNER_KEY_PARAMETER",
    "ANTHROPIC_API_KEY": "ANTHROPIC_API_KEY_PARAMETER",
    "PAWPAL_ORIGIN_VERIFY_SECRET": "PAWPAL_ORIGIN_VERIFY_PARAMETER",
}


def load_secrets_from_ssm(client: Optional[Any] = None) -> list[str]:
    """Fill each unset secret variable from its SSM parameter; return the
    variable names that were loaded."""
    wanted = {
        env: os.environ[param_env].strip()
        for env, param_env in SECRET_PARAMETERS.items()
        if os.getenv(param_env, "").strip() and not os.getenv(env, "").strip()
    }
    if not wanted:
        return []
    try:
        if client is None:
            import boto3

            client = boto3.client("ssm")
        resp = client.get_parameters(Names=sorted(set(wanted.values())), WithDecryption=True)
    except Exception:
        _log.exception("Could not read secrets from SSM: %s", sorted(set(wanted.values())))
        return []

    values = {p["Name"]: p["Value"] for p in resp.get("Parameters", [])}
    if resp.get("InvalidParameters"):
        _log.error("SSM parameters not found: %s", sorted(resp["InvalidParameters"]))
    loaded = []
    for env, name in wanted.items():
        value = values.get(name, "").strip()
        if value:
            os.environ[env] = value
            loaded.append(env)
    return sorted(loaded)
