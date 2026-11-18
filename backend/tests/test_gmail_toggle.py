import pytest
from fastapi.testclient import TestClient

import main
from config import Settings, settings


@pytest.mark.parametrize(
    ("client_id", "secret", "expected"),
    [
        ("123.apps.googleusercontent.com", "GOCSPX-abc", True),
        ("", "", False),
        ("your_google_client_id.apps.googleusercontent.com", "your_google_client_secret", False),
        ("placeholder", "placeholder", False),
        ("123.apps.googleusercontent.com", "", False),
    ],
)
def test_google_configured_detects_placeholders(client_id, secret, expected):
    s = Settings(google_client_id=client_id, google_client_secret=secret)
    assert s.google_configured is expected


def test_options_and_login_when_google_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "your_google_client_id")
    client = TestClient(main.app, follow_redirects=False)
    assert client.get("/auth/options").json()["gmail"] is False
    resp = client.get("/auth/login")
    assert resp.headers["location"].endswith("/?auth_error=gmail_disabled")
    resp = client.get("/auth/callback?code=x&state=y")
    assert resp.headers["location"].endswith("/?auth_error=gmail_disabled")


def test_gmail_enabled_switch_hides_configured_google(monkeypatch):
    monkeypatch.setattr(settings, "gmail_enabled", False)
    assert TestClient(main.app).get("/auth/options").json() == {
        "demo": True,
        "demoAccessCodeRequired": False,
        "gmail": False,
    }


def test_options_when_google_configured():
    assert TestClient(main.app).get("/auth/options").json()["gmail"] is True
