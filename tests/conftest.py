import os
from pathlib import Path

import pytest

# Ensure modern protobuf works cleanly with steam.client across all test runs
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def golden_single_vdf(fixtures_dir: Path) -> Path:
    return fixtures_dir / "golden_bazzite_single.vdf"


@pytest.fixture
def golden_multi_vdf(fixtures_dir: Path) -> Path:
    return fixtures_dir / "golden_bazzite_multi.vdf"
