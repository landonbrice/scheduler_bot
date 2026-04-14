import json
from pathlib import Path
import pytest


@pytest.fixture
def tmp_tasks_path(tmp_path: Path) -> Path:
    p = tmp_path / "tasks.json"
    p.write_text("[]")
    return p
