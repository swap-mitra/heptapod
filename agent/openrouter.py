"""Minimal client for OpenRouter's chat-completions API, which serves many models, free ones
included, behind one OpenAI-style interface. Stdlib HTTP, so no extra dependency."""

import json
import time
import urllib.error
import urllib.request
from typing import Any

BASE_URL = "https://openrouter.ai/api/v1"
ATTEMPTS = 3
RETRYABLE = {429, 502, 503}  # free models are rate limited often; these clear on their own
TIMEOUT_S = 120


class OpenRouterClient:
    def __init__(self, api_key: str, base_url: str = BASE_URL):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def complete(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST one chat-completions request and return the response body.

        Retries rate limits and transient upstream errors, then raises RuntimeError with
        OpenRouter's own message for anything it cannot recover from."""
        request = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=json.dumps(payload).encode(),
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "X-Title": "heptapod",
            },
        )
        for attempt in range(1, ATTEMPTS + 1):
            try:
                with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
                    body = json.load(response)
            except urllib.error.HTTPError as exc:
                if exc.code in RETRYABLE and attempt < ATTEMPTS:
                    time.sleep(_retry_delay(exc, attempt))
                    continue
                raise RuntimeError(f"OpenRouter returned HTTP {exc.code}: {_detail(exc)}") from exc
            if "error" in body:
                raise RuntimeError(f"OpenRouter error: {body['error'].get('message', body['error'])}")
            return body
        raise AssertionError("unreachable")


def _retry_delay(exc: urllib.error.HTTPError, attempt: int) -> float:
    try:
        return float(exc.headers.get("Retry-After"))
    except (TypeError, ValueError):
        return 2.0**attempt


def _detail(exc: urllib.error.HTTPError) -> str:
    try:
        return str(json.load(exc)["error"]["message"])
    except (ValueError, KeyError, TypeError, OSError):
        return str(exc.reason)
