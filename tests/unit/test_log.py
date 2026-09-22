from pathlib import Path
from unittest.mock import patch

from core.log import get_logger, get_recent_log_lines, setup_logging


def test_logger_hierarchy():
    log = get_logger("core.steam")
    assert log.name == "ssm.steam"


def test_setup_logging_and_write(tmp_path: Path):
    with patch("core.log.get_log_dir", return_value=tmp_path):
        log_file = setup_logging()
        assert log_file.parent == tmp_path

        log = get_logger("test")
        log.info("Test message for log verification")

        lines = get_recent_log_lines(10)
        assert any("Test message for log verification" in line for line in lines)
