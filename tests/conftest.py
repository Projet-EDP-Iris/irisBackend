"""
Shared pytest configuration.

Each test module sets app.dependency_overrides[get_db] at import time.
Since all modules are imported at collection time, the last import wins and
all tests would use the wrong DB. This autouse fixture re-applies the correct
override from the test's own module before each test.
"""
import pytest

from app.db.database import get_db
from app.main import app


@pytest.fixture(autouse=True)
def set_db_override(request):
    module = request.module
    if hasattr(module, "override_get_db"):
        app.dependency_overrides[get_db] = module.override_get_db
    yield
    if hasattr(module, "override_get_db"):
        app.dependency_overrides.pop(get_db, None)
