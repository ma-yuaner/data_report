import pytest

from data_report_api import create_app
from data_report_api.config import TestConfig


@pytest.fixture()
def client():
    app = create_app(TestConfig)
    return app.test_client()

