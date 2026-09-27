import base64

import pytest

from core.auth import ConfigError, SecretResolver, resolve


def test_api_key_header(monkeypatch):
    monkeypatch.setenv("T_KEY", "k1")
    assert resolve({"type": "api_key", "header": "X-API-Key", "secret_ref": "T_KEY"}) == {"X-API-Key": "k1"}


def test_basic_header(monkeypatch):
    monkeypatch.setenv("T_USER", "u")
    monkeypatch.setenv("T_PASS", "p:w")
    headers = resolve({"type": "basic", "username_ref": "T_USER", "password_ref": "T_PASS"})
    assert headers == {"Authorization": "Basic " + base64.b64encode(b"u:p:w").decode()}


def test_missing_secret_names_the_ref(monkeypatch):
    monkeypatch.delenv("T_MISSING", raising=False)
    with pytest.raises(ConfigError, match="T_MISSING"):
        SecretResolver().get("T_MISSING")


def test_unknown_scheme_fails():
    with pytest.raises(ConfigError, match="kerberos"):
        resolve({"type": "kerberos"})
