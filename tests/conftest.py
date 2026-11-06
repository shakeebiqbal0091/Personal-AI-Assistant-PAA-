import pytest

from app.database import db


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Every test gets its own SQLite file; the dev DB is never touched.

    get_connection() reads DEFAULT_DB_PATH at call time, so patching the
    module attribute covers TaskManager and ConversationRepository defaults.
    """
    monkeypatch.setattr(db, "DEFAULT_DB_PATH", tmp_path / "paa_test.db")