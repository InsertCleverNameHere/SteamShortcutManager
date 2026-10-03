"""
tests/unit/test_prefix_store.py
Tests persistent prefix override storage and atomic file updates.
"""

from pathlib import Path

import pytest

from core import prefix_store


@pytest.fixture
def isolated_prefix_file(tmp_path, monkeypatch):
    test_file = tmp_path / "prefixes.json"
    monkeypatch.setattr(prefix_store, "get_prefixes_file", lambda: test_file)
    return test_file


def test_prefix_store_lifecycle(isolated_prefix_file):
    appid = "123456"

    # Initially empty
    assert prefix_store.get_prefix_override(appid) is None
    assert prefix_store.clear_prefix_override(appid) is False

    # Set override
    target_path = Path("/mock/wine/prefix")
    prefix_store.set_prefix_override(appid, target_path)

    stored = prefix_store.get_prefix_override(appid)
    assert stored is not None
    assert str(stored) == str(target_path.resolve())

    # Clear override
    assert prefix_store.clear_prefix_override(appid) is True
    assert prefix_store.get_prefix_override(appid) is None


def test_prefix_store_handles_corrupt_file(isolated_prefix_file):
    isolated_prefix_file.write_text("invalid json content {{{", encoding="utf-8")
    assert prefix_store.load_prefix_overrides() == {}
    assert prefix_store.get_prefix_override("1234") is None
