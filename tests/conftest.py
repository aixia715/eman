import pytest
from fastapi.testclient import TestClient

from eman.main import create_app


@pytest.fixture()
def client():
    app = create_app(":memory:")
    with TestClient(app) as c:
        yield c
