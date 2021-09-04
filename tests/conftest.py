from unittest import mock
import os
import pytest


@pytest.fixture(autouse=True)
def mock_settings_env_vars():
    with mock.patch.dict(os.environ, {"DATASETTE_API_TOKEN": "fake-token"}):
        yield
