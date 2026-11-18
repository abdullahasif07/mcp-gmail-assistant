from fastapi.testclient import TestClient

import main

client = TestClient(main.app, follow_redirects=False)


def test_health():
    assert client.get("/").json() == {"status": "running"}


def test_protected_routes_require_session():
    assert client.get("/emails").status_code == 401
    assert client.get("/auth/me").status_code == 401
    assert client.post("/chat", json={"message": "hi"}).status_code == 401


def test_login_sets_state_cookie_and_redirects_to_google():
    resp = client.get("/auth/login")
    assert resp.status_code == 307
    assert resp.headers["location"].startswith("https://accounts.google.com/")
    assert "state=" in resp.headers["location"]
    assert "mm_oauth_state" in resp.cookies


def test_callback_rejects_missing_or_forged_state():
    fresh = TestClient(main.app, follow_redirects=False)
    resp = fresh.get("/auth/callback?code=abc&state=forged")
    assert resp.headers["location"].endswith("/?auth_error=invalid_state")

    fresh.get("/auth/login")
    resp = fresh.get("/auth/callback?code=abc&state=forged")
    assert resp.headers["location"].endswith("/?auth_error=invalid_state")


def test_callback_forwards_consent_denial_to_frontend():
    resp = client.get("/auth/callback?error=access_denied")
    assert resp.headers["location"] == "http://localhost:3000/?auth_error=access_denied"
