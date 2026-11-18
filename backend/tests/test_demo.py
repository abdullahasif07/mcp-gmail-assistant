import asyncio

import pytest
from fastapi.testclient import TestClient

import main
from config import settings
from routes import auth as auth_routes
from routes.emails import _parse_list_blob, _parse_read_message
from services import usage
from services.demo_mailbox import DemoMailbox
from services.mcp_service import MCPToolError


def run(coro):
    return asyncio.run(coro)


def list_ids(box: DemoMailbox, query: str, n: int = 50) -> list[str]:
    text = run(box.call_tool("gmail_list_messages", {"query": query, "maxResults": n}))
    return [e.id for e in _parse_list_blob(text)]


# ── Mailbox / search ──────────────────────────────────────────────────────


def test_search_operators():
    box = DemoMailbox.seeded()
    inbox = list_ids(box, "in:inbox")
    sent = list_ids(box, "in:sent")
    assert inbox and sent and not set(inbox) & set(sent)
    assert set(list_ids(box, "from:marcus")) == {"m03", "m05"}
    assert set(list_ids(box, "is:unread")) <= set(inbox)
    assert "m01" in list_ids(box, "is:unread newer_than:1d")
    assert "m17" not in list_ids(box, "newer_than:7d")
    assert list_ids(box, "label:receipts") == ["m10", "m12"]
    assert list_ids(box, '"talk proposal"') == ["m11"]
    assert "m17" not in list_ids(box, "in:inbox -category:promotions")
    assert list_ids(box, "subject:nonexistent") == []


def test_list_respects_max_results_and_newest_first():
    box = DemoMailbox.seeded()
    ids = list_ids(box, "in:inbox", n=3)
    assert ids == ["m01", "m02", "m05"]


def test_output_parses_like_real_mcp_server():
    box = DemoMailbox.seeded()
    text = run(box.call_tool("gmail_read_message", {"messageId": "m02"}))
    email = _parse_read_message(text, "m02")
    assert email.sender.startswith("Priya Shah")
    assert email.threadId == "t-recruiter"
    assert "Lumen Health" in email.body

    thread = run(box.call_tool("gmail_get_thread", {"threadId": "t-launch"}))
    assert thread.count("---") == 2


def test_send_goes_to_sent_and_threads_replies():
    box = DemoMailbox.seeded()
    result = run(
        box.call_tool(
            "gmail_send_message",
            {
                "to": "marcus.chen@lumacorp.example",
                "subject": "Re: Project Atlas launch plan",
                "body": "PR landed, we're on track.",
                "replyToMessageId": "m05",
            },
        )
    )
    assert "not actually delivered" in result
    assert list_ids(box, "in:sent", n=1) == ["sent-1"]
    thread = run(box.call_tool("gmail_get_thread", {"threadId": "t-launch"}))
    assert "PR landed" in thread


def test_unknown_message_and_tool_raise_tool_errors():
    box = DemoMailbox.seeded()
    with pytest.raises(MCPToolError):
        run(box.call_tool("gmail_read_message", {"messageId": "nope"}))
    with pytest.raises(MCPToolError):
        run(box.call_tool("gmail_delete_everything", {}))


# ── HTTP flow ─────────────────────────────────────────────────────────────


def demo_client(access_code: str | None = None) -> TestClient:
    client = TestClient(main.app)
    body = {"accessCode": access_code} if access_code is not None else {}
    resp = client.post("/auth/demo", json=body)
    assert resp.status_code == 200, resp.text
    return client


def test_demo_session_end_to_end():
    client = demo_client()
    me = client.get("/auth/me").json()
    assert me["mode"] == "demo"

    emails = client.get("/emails", params={"query": "in:inbox"}).json()["emails"]
    assert emails[0]["from"].startswith("Hannah")

    detail = client.get(f"/emails/{emails[0]['id']}").json()
    assert "cracked" in detail["body"]

    sent = client.post(
        "/emails/send",
        json={"to": "hannah.okafor@brightmail.example", "subject": "Re: Order", "body": "So sorry!"},
    ).json()
    assert "not actually delivered" in sent["detail"]

    assert client.post("/chat/confirm", json={
        "tool": "gmail_send_message",
        "args": {"to": "x@y.example", "subject": "s", "body": "b"},
    }).status_code == 200

    assert client.post("/auth/logout").json() == {"ok": True}
    assert client.get("/auth/me").status_code == 401


def test_demo_sessions_are_isolated():
    a, b = demo_client(), demo_client()
    a.post("/emails/send", json={"to": "x@y.example", "subject": "only in A", "body": "hi"})
    a_sent = [e["subject"] for e in a.get("/emails", params={"query": "in:sent"}).json()["emails"]]
    b_sent = [e["subject"] for e in b.get("/emails", params={"query": "in:sent"}).json()["emails"]]
    assert "only in A" in a_sent
    assert "only in A" not in b_sent


def test_demo_access_code(monkeypatch):
    monkeypatch.setattr(settings, "demo_access_code", "letmein")
    monkeypatch.setattr(auth_routes, "demo_code_attempts", usage.SlidingWindowLimiter(3, 600))
    client = TestClient(main.app)
    assert client.get("/auth/demo").json() == {"enabled": True, "accessCodeRequired": True}
    assert client.post("/auth/demo", json={}).status_code == 403
    assert client.post("/auth/demo", json={"accessCode": "wrông"}).status_code == 403
    assert client.post("/auth/demo", json={"accessCode": "letmein"}).status_code == 200
    # Fourth attempt from the same IP within the window is rate limited.
    assert client.post("/auth/demo", json={"accessCode": "letmein"}).status_code == 429


def test_demo_disabled(monkeypatch):
    monkeypatch.setattr(settings, "demo_enabled", False)
    assert TestClient(main.app).post("/auth/demo", json={}).status_code == 404


def test_ai_budget_caps(monkeypatch):
    monkeypatch.setattr(settings, "demo_session_ai_limit", 0)
    client = demo_client()
    resp = client.post("/ai/suggest-reply", json={"emailId": "m01"})
    assert resp.status_code == 429
    assert "demo session" in resp.json()["detail"]

    monkeypatch.setattr(settings, "demo_session_ai_limit", 5)
    monkeypatch.setattr(settings, "ai_daily_limit", 1)
    monkeypatch.setattr(usage, "daily_ai_requests", usage.DailyCounter())
    usage.daily_ai_requests.try_consume(1)  # budget already used today
    resp = client.post("/chat", json={"message": "hi"})
    assert resp.status_code == 429
    assert "daily AI budget" in resp.json()["detail"]


def test_chat_history_endpoints():
    client = demo_client()
    assert client.get("/chat/history").json() == {"messages": [], "pendingAction": None}
    client.post("/chat/confirm", json={
        "tool": "gmail_send_message",
        "args": {"to": "x@y.example", "subject": "s", "body": "b"},
    })
    msgs = client.get("/chat/history").json()["messages"]
    assert msgs[-1]["role"] == "assistant" and "saved to Sent" in msgs[-1]["text"]
    assert client.delete("/chat/history").json() == {"ok": True}
    assert client.get("/chat/history").json()["messages"] == []


def test_discard_forgets_pending_draft():
    from routes.chat import conversation_key
    from services.chat_memory import chat_memory

    client = demo_client()
    session_id = client.get("/auth/me").json()["userId"]
    conv = chat_memory.get(conversation_key(type("S", (), {"mode": "demo", "id": session_id})()))
    conv.pending = {"tool": "gmail_send_message", "args": {"to": "a@b.example"}}
    assert client.get("/chat/history").json()["pendingAction"] is not None
    client.post("/chat/discard")
    body = client.get("/chat/history").json()
    assert body["pendingAction"] is None
    assert body["messages"][-1]["text"] == "Draft discarded."
