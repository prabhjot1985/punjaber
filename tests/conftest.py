"""Point every test at a throwaway database before the app modules import it."""

import os
import tempfile
from pathlib import Path

import pytest

# Must be set before app.db is imported, since DB_PATH is read at import time.
_TMP_DIR = Path(tempfile.mkdtemp(prefix="punjaber-tests-"))
os.environ["PUNJABER_DB"] = str(_TMP_DIR / "test.db")
os.environ["PUNJABER_RECORDINGS"] = str(_TMP_DIR / "recordings")
os.environ["PUNJABER_AUDIO"] = str(_TMP_DIR / "audio")

from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    db.init()
    with TestClient(app) as test_client:
        test_client.headers["X-Punjaber-User"] = "pytest"
        test_client.post("/api/reset")
        yield test_client
        test_client.post("/api/reset")


@pytest.fixture()
def user():
    db.init()
    db.reset("pytest-unit")
    yield "pytest-unit"
    db.reset("pytest-unit")
