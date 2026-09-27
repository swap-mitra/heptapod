"""Auth Layer: turns an adapter's auth config into request headers (HLD: Auth Translation
Design, PRD: FR3). Adapter authors never build auth themselves."""

import base64
import os

# An adapter's declared scheme, e.g. {"type": "api_key", "header": "X-API-Key", "secret_ref": "CRM_API_KEY"}.
AuthConfig = dict[str, str]
# Request headers to merge into the backend request.
Credentials = dict[str, str]


class ConfigError(Exception):
    """Misconfiguration detected at startup: bad adapters.toml, missing secret, unknown auth scheme."""


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
    raise ConfigError(f"unknown auth scheme {scheme!r}")
