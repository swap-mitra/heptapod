"""Auth Layer: turns an adapter's auth config into request headers (HLD: Auth Translation
Design, PRD: FR3). Adapter authors never build auth themselves."""

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

# An adapter's declared scheme, e.g. {"type": "api_key", "header": "X-API-Key", "secret_ref": "CRM_API_KEY"}.
AuthConfig = dict[str, str]
# Request headers to merge into the backend request.
Credentials = dict[str, str]


class ConfigError(Exception):
    """Misconfiguration detected at startup: bad adapters.toml, missing secret, unknown auth scheme."""


class AuthError(Exception):
    """A credential exchange failed, e.g. the OAuth2 token endpoint rejected the client."""


class SecretResolver:
    """Looks up secrets by reference name. Reads env vars in v1; a vault client replaces this class."""

    def get(self, ref: str) -> str:
        value = os.environ.get(ref)
        if not value:
            raise ConfigError(f"secret {ref!r} is not set in the environment")
        return value


def resolve(config: AuthConfig, secrets: SecretResolver | None = None) -> Credentials:
    """Produce the request headers for one adapter's auth config."""
    secrets = secrets or SecretResolver()
    scheme = config.get("type")
    if scheme == "api_key":
        return {config["header"]: secrets.get(config["secret_ref"])}
    if scheme == "basic":
        pair = f"{secrets.get(config['username_ref'])}:{secrets.get(config['password_ref'])}"
        return {"Authorization": "Basic " + base64.b64encode(pair.encode()).decode()}
    if scheme == "oauth2_cc":
        return {"Authorization": "Bearer " + _oauth2_token(config, secrets)}
    raise ConfigError(f"unknown auth scheme {scheme!r}")


# Bearer tokens by (token_url, client_id) -> (token, monotonic time to refresh at).
_tokens: dict[tuple[str, str], tuple[str, float]] = {}
# Refresh this long before the server's expiry, so a token never lapses mid-request.
REFRESH_MARGIN_S = 10
TIMEOUT_S = 10


def _oauth2_token(config: AuthConfig, secrets: SecretResolver) -> str:
    client_id = secrets.get(config["client_id_ref"])
    key = (config["token_url"], client_id)
    token, refresh_at = _tokens.get(key, ("", 0.0))
    if time.monotonic() >= refresh_at:
        token, expires_in = _fetch_token(config["token_url"], client_id, secrets.get(config["client_secret_ref"]))
        _tokens[key] = (token, time.monotonic() + max(expires_in - REFRESH_MARGIN_S, 0))
    return token


def _fetch_token(url: str, client_id: str, client_secret: str) -> tuple[str, float]:
    """OAuth2 client-credentials grant (RFC 6749 section 4.4); returns (token, lifetime in s)."""
    form = {"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret}
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(form).encode(),
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
            body = json.load(response)
        # expires_in is optional in the spec; without it, fetch a fresh token every time.
        return body["access_token"], float(body.get("expires_in", 0))
    except urllib.error.HTTPError as exc:
        raise AuthError(f"OAuth2 token request to {url} was rejected: HTTP {exc.code}") from exc
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise AuthError(f"OAuth2 token request to {url} failed: {exc}") from exc
