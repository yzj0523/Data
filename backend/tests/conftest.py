import os

import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch, tmp_path):
    """Tests must not read a developer's credentials or local .env file."""
    for name in os.environ:
        if name.upper().startswith("AI_"):
            monkeypatch.delenv(name)
    monkeypatch.chdir(tmp_path)
