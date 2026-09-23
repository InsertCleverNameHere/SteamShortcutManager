from pathlib import Path

from core.pe_info import get_game_name_from_pe


def test_get_game_name_fallback_on_non_exe(tmp_path: Path):
    txt_file = tmp_path / "game_text.txt"
    txt_file.write_text("not an exe")
    assert get_game_name_from_pe(txt_file) == "game_text"


def test_get_game_name_fallback_on_nonexistent_file(tmp_path: Path):
    missing_exe = tmp_path / "super_mario.exe"
    assert get_game_name_from_pe(missing_exe) == "super_mario"


def test_get_game_name_fallback_on_corrupt_exe(tmp_path: Path):
    corrupt_exe = tmp_path / "corrupt_game.exe"
    corrupt_exe.write_bytes(b"MZ\x00\x00FAKE_PE_HEADER_DATA")
    assert get_game_name_from_pe(corrupt_exe) == "corrupt_game"
