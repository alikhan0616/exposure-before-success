"""Shared test fixtures.

Also puts the harness root on `sys.path` so `import src...` works whether
pytest is invoked as `pytest` or `python -m pytest`, from any directory.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.environments import make_environment  # noqa: E402
from src.task_types import USER_TASKS_BY_ID  # noqa: E402

FIXTURES_DIR = REPO_ROOT / "fixtures"


@pytest.fixture
def inbox_fixture_path() -> str:
    return str(FIXTURES_DIR / "inbox_seed.json")


@pytest.fixture
def calendar_fixture_path() -> str:
    return str(FIXTURES_DIR / "calendar_seed.json")


@pytest.fixture
def web_fixture_path() -> str:
    return str(FIXTURES_DIR / "web_search_seed.json")


@pytest.fixture
def inbox(inbox_fixture_path):
    """Fresh inbox seeded from the fixture."""
    return make_environment("inbox", inbox_fixture_path)


@pytest.fixture
def calendar(calendar_fixture_path):
    """Fresh calendar seeded from the fixture."""
    return make_environment("calendar", calendar_fixture_path)


@pytest.fixture
def search_index(web_fixture_path):
    """Fresh search index seeded from the fixture."""
    return make_environment("web_search", web_fixture_path)


@pytest.fixture
def env_for_task():
    """Callable: user_task_id -> (UserTask, fresh environment for it)."""

    def _make(user_task_id: str):
        task = USER_TASKS_BY_ID[user_task_id]
        return task, make_environment(task.environment, task.fixture_path)

    return _make
