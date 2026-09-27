import logging

import pytest

from core.adapter import AdapterResult
from core.auth import ConfigError, Credentials
from core.registry import Registry


class FakeAdapter:
    """Records what the registry handed it; configured through constructor kwargs like a real adapter."""

    description = "fake"
    input_schema = {"type": "object", "properties": {"operation": {"enum": ["ping", "boom"]}}}

    def __init__(self, name: str, base_url: str):
        self.name = name
        self.base_url = base_url
        self.auth_config = {"type": "api_key", "header": "X-Key", "secret_ref": "FAKE_KEY"}
        self.calls = []

    def execute(self, input: dict, credentials: Credentials) -> AdapterResult:
        if input.get("operation") == "boom":
            raise RuntimeError("adapter bug")
        self.calls.append((input, credentials))
        return AdapterResult(success=True, data={"from": self.name})


@pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_KEY", "secret")
    path = tmp_path / "adapters.toml"
    path.write_text(
        '[a]\nclass = "tests.test_registry:FakeAdapter"\nname = "alpha"\nbase_url = "http://a"\n'
        '[b]\nclass = "tests.test_registry:FakeAdapter"\nname = "beta"\nbase_url = "http://b"\n'
    )
    return path


def test_loads_every_configured_adapter_as_a_tool(config):
    tools = Registry.from_config(config).tools()
    assert [t["name"] for t in tools] == ["alpha", "beta"]
    assert tools[0] == {"name": "alpha", "description": "fake", "input_schema": FakeAdapter.input_schema}


def test_routes_call_with_resolved_credentials(config):
    registry = Registry.from_config(config)
    result = registry.call("beta", {"operation": "ping"})
    assert result == AdapterResult(success=True, data={"from": "beta"})
    beta = registry.adapters["beta"]
    assert beta.base_url == "http://b"
    assert beta.calls == [({"operation": "ping"}, {"X-Key": "secret"})]
    assert registry.adapters["alpha"].calls == []


def test_unknown_tool_is_a_structured_error(config):
    result = Registry.from_config(config).call("gamma", {})
    assert not result.success and "gamma" in result.error


def test_adapter_exception_becomes_failed_result(config, caplog):
    with caplog.at_level(logging.ERROR):
        result = Registry.from_config(config).call("alpha", {"operation": "boom"})
    assert not result.success and "adapter bug" in result.error
    assert any(r.levelno == logging.ERROR and r.exc_info for r in caplog.records)


def test_each_call_logs_system_operation_latency_outcome(config, caplog):
    registry = Registry.from_config(config)
    with caplog.at_level(logging.INFO, logger="core.registry"):
        registry.call("alpha", {"operation": "ping"})
        registry.call("alpha", {"operation": "boom"})
    calls = [r for r in caplog.records if hasattr(r, "latency_ms")]
    assert [(r.system, r.operation, r.success) for r in calls] == [("alpha", "ping", True), ("alpha", "boom", False)]
    assert all(r.latency_ms >= 0 for r in calls)


def test_missing_secret_fails_at_startup(config, monkeypatch):
    monkeypatch.delenv("FAKE_KEY")
    with pytest.raises(ConfigError, match="FAKE_KEY"):
        Registry.from_config(config)


@pytest.mark.parametrize(
    "toml, match",
    [
        ('[a]\nbase_url = "x"\n', "class"),
        ('[a]\nclass = "tests.test_registry.FakeAdapter"\n', "module:Class"),
        ('[a]\nclass = "tests.nope:FakeAdapter"\n', "tests.nope"),
        ('[a]\nclass = "tests.test_registry:FakeAdapter"\nname = "x"\n', "constructor"),
        ('[a]\nclass = "tests.test_registry:FakeAdapter"\nname = "x"\nbase_url = "u"\n'
         '[b]\nclass = "tests.test_registry:FakeAdapter"\nname = "x"\nbase_url = "u"\n', "duplicate"),
    ],
)
def test_bad_config_fails_at_startup(tmp_path, monkeypatch, toml, match):
    monkeypatch.setenv("FAKE_KEY", "secret")
    path = tmp_path / "adapters.toml"
    path.write_text(toml)
    with pytest.raises(ConfigError, match=match):
        Registry.from_config(path)
