import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from agent.openrouter import OpenRouterClient
from tests.conftest import serve

OK = {"choices": [{"message": {"role": "assistant", "content": "hi"}, "finish_reason": "stop"}]}


def fake_openrouter(replies):
    """An OpenRouter stand-in that returns `replies` in order and records each request."""
    app = FastAPI()
    app.state.requests = []

    @app.post("/chat/completions")
    async def complete(request: Request):
        app.state.requests.append({"auth": request.headers.get("authorization"), "body": await request.json()})
        status, body = replies.pop(0)
        return JSONResponse(body, status_code=status, headers={"Retry-After": "0"} if status == 429 else None)

    return app


def test_sends_payload_with_bearer_key():
    app = fake_openrouter([(200, OK)])
    with serve(app) as url:
        assert OpenRouterClient("k1", base_url=url).complete({"model": "m"}) == OK
    assert app.state.requests == [{"auth": "Bearer k1", "body": {"model": "m"}}]


def test_retries_rate_limit_then_succeeds():
    app = fake_openrouter([(429, {"error": {"message": "slow down"}}), (200, OK)])
    with serve(app) as url:
        assert OpenRouterClient("k", base_url=url).complete({}) == OK
    assert len(app.state.requests) == 2


def test_gives_up_after_repeated_rate_limits():
    app = fake_openrouter([(429, {"error": {"message": "slow down"}})] * 3)
    with serve(app) as url, pytest.raises(RuntimeError, match="429.*slow down"):
        OpenRouterClient("k", base_url=url).complete({})


def test_auth_failure_is_not_retried():
    app = fake_openrouter([(401, {"error": {"message": "No auth credentials found"}})])
    with serve(app) as url, pytest.raises(RuntimeError, match="401.*No auth credentials"):
        OpenRouterClient("k", base_url=url).complete({})
    assert len(app.state.requests) == 1


def test_error_in_ok_body_raises():
    # OpenRouter can report an upstream provider failure inside a 200 response.
    app = fake_openrouter([(200, {"error": {"message": "provider down", "code": 502}})])
    with serve(app) as url, pytest.raises(RuntimeError, match="provider down"):
        OpenRouterClient("k", base_url=url).complete({})
