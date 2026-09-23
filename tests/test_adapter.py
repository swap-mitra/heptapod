from core.adapter import Adapter, AdapterResult, Credentials


class EchoAdapter:
    name = "echo"
    description = "Returns its input."
    input_schema = {"type": "object"}
    auth_config = {"type": "api_key", "header": "X-API-Key", "secret_ref": "ECHO_KEY"}

    def execute(self, input: dict, credentials: Credentials) -> AdapterResult:
        return AdapterResult(success=True, data=input)


def test_structural_adapter_satisfies_protocol():
    adapter: Adapter = EchoAdapter()
    assert adapter.execute({"a": 1}, {}) == AdapterResult(success=True, data={"a": 1})


def test_failure_result_defaults():
    result = AdapterResult(success=False, error="boom")
    assert result.data is None and result.error == "boom"
