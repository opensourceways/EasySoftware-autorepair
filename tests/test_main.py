from fastapi.testclient import TestClient
from app.config import settings
from app.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "env": settings.env}


def test_webhook_endpoint():
    test_payload = {
        "event": "test.event",
        "data": {"key": "value"}
    }
    response = client.post("/api/v1/webhooks/spec", json=test_payload)
    assert response.status_code == 200
