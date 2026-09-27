from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_every_adapter_has_its_own_test_file():
    # AGENTS.md: an adapter PR without its own test file must fail CI, not just review.
    missing = [
        p.name
        for p in (ROOT / "adapters").glob("*.py")
        if p.name != "__init__.py" and not (ROOT / "tests" / f"test_{p.name}").exists()
    ]
    assert not missing, f"adapters without tests/test_<name>.py: {missing}"
