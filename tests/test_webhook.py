import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

VALID_SIGNATURE = "d033c8d9c1a3e7f9c1d4d1b15b3c1d4d1b15b3c1d4d1b15b3c1d4d1b15b3c1d"


@pytest.fixture
def valid_payload():
    return {
        "pull_request": {"number": 123},
        "project": {
            "namespace": "opensource",
            "name": "awesome-project"
        }
    }


def test_valid_webhook(valid_payload):
    response = client.post(
        "/api/v1/webhooks/spec",
        json=valid_payload,
        headers={"X-Signature": VALID_SIGNATURE}
    )
    assert response.status_code == 200
    assert "processing" in response.json()["status"]


def test_invalid_signature(valid_payload):
    response = client.post(
        "/api/v1/webhooks/spec",
        json=valid_payload,
        headers={"X-Signature": "invalid_signature"}
    )
    assert response.status_code == 403
    assert "Invalid signature" in response.json()["detail"]
