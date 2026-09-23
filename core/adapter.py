"""The Adapter contract every backend implements (HLD: Adapter Contract, PRD: FR1, FR7)."""

from dataclasses import dataclass
from typing import Any, Protocol

# Shapes owned by the Auth Layer (HLD: Auth Translation Design). Plain dicts until
# core/auth.py exists and gives them a real type.
AuthConfig = dict[str, str]
Credentials = dict[str, str]


@dataclass
class AdapterResult:
    """Outcome of one adapter call. A backend failure is data (success=False, error set),
    never a raised exception."""

    success: bool
    data: dict[str, Any] | None = None
    error: str | None = None


class Adapter(Protocol):
    """One backend, exposed to the agent as one tool."""

    name: str
    description: str
    input_schema: dict[str, Any]  # JSON schema exposed to the agent as the tool's parameters
    auth_config: AuthConfig  # what the Auth Layer needs to authenticate this adapter's calls

    def execute(self, input: dict[str, Any], credentials: Credentials) -> AdapterResult:
        """Perform the operation against the backend and return a structured result
        or a structured error, never a raw exception."""
        ...
