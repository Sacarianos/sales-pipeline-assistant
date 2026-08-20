import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from acme.loading import load_data


@pytest.fixture(scope="session")
def data():
    """The loader is a fixture, not a seam. Loaded once per test session."""
    return load_data()
