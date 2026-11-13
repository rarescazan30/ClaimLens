from fastapi.testclient import TestClient


def test_health():
    from app.main import app
    assert TestClient(app).get("/health").json() == {"ok": True}
