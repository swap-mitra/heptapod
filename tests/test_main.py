import os

import pytest

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
