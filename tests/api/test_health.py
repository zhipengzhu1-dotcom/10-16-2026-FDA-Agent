from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from fda_copilot.api.app import app, database_url


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health_reports_database_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok"}


def test_health_reports_unreachable_database(client: TestClient) -> None:
    app.dependency_overrides[database_url] = lambda: "postgresql://fda:fda@127.0.0.1:1/fda"

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "error", "db": "unreachable"}
