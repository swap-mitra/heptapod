import io
import os
import sys
from types import SimpleNamespace

import pytest

import agent.__main__ as cli
from agent.__main__ import load_dotenv


def test_fills_unset_vars_and_keeps_existing(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text('# comment\n\nT_NEW = "quoted value"\nT_EXISTING=from-file\nT_EMPTY=\n')
    monkeypatch.delenv("T_NEW", raising=False)
    monkeypatch.delenv("T_EMPTY", raising=False)
    monkeypatch.setenv("T_EXISTING", "from-shell")
    load_dotenv(env)
    assert (os.environ["T_NEW"], os.environ["T_EXISTING"]) == ("quoted value", "from-shell")
    # A blank placeholder is treated as unset, so it can't mask a missing-secret error.
    assert "T_EMPTY" not in os.environ


def test_missing_file_is_fine(tmp_path):
    load_dotenv(tmp_path / "absent.env")


def test_malformed_line_names_the_line_not_its_content(tmp_path):
    env = tmp_path / ".env"
    env.write_text("A=1\nsk-or-pasted-key-without-name\n")
    with pytest.raises(SystemExit) as exc:
        load_dotenv(env)
    assert "line 2" in str(exc.value) and "sk-or" not in str(exc.value)


def test_answer_prints_on_a_console_that_cannot_encode_it(monkeypatch, tmp_path):
    # Windows consoles default to cp1252; models freely answer with characters like "→".
    console = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", newline="\n")
    monkeypatch.setattr(sys, "stdout", console)
    monkeypatch.setattr(sys, "argv", ["agent", "task"])
    monkeypatch.chdir(tmp_path)  # no .env here
    monkeypatch.setenv("HEPTAPOD_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setattr(cli, "Registry", SimpleNamespace(from_config=lambda path: None))
    monkeypatch.setattr(cli, "run_openrouter", lambda *args, **kwargs: "T-9004 → in_progress")
    cli.main()
    console.flush()
    assert console.buffer.getvalue() == b"T-9004 ? in_progress\n"
