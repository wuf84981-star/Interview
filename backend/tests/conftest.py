import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import app.tools  # noqa: E402,F401  导入即完成四个工具的注册
from app.config import Settings  # noqa: E402
from app.session.store import SessionStore  # noqa: E402


@pytest.fixture
def settings() -> Settings:
    return Settings(llm_mock=True)


@pytest.fixture
def store() -> SessionStore:
    return SessionStore()


@pytest.fixture
def session(store: SessionStore):
    return store.create()
