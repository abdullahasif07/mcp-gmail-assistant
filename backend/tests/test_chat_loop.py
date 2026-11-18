"""Drive the full chat tool loop against the demo mailbox with a scripted
fake OpenAI client (no network)."""

import asyncio
import json

from openai.types.chat import ChatCompletion

from services import ai_service
from services.chat_memory import Conversation, _trim
from services.demo_mailbox import DemoMailbox

FAKE_TOOLS = [
    {"type": "function", "function": {"name": n, "description": "", "parameters": {}}}
    for n in ("gmail_list_messages", "gmail_read_message", "gmail_send_message")
]


def _completion(content=None, tool_calls=None) -> ChatCompletion:
    message = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = [
            {
                "id": f"call_{i}",
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(args)},
            }
            for i, (name, args) in enumerate(tool_calls)
        ]
    return ChatCompletion.model_validate(
        {
            "id": "cmpl",
            "object": "chat.completion",
            "created": 0,
            "model": "fake",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "tool_calls" if tool_calls else "stop",
                    "message": message,
                }
            ],
        }
    )


class FakeCompletions:
    def __init__(self, script):
        self.script = list(script)
        self.requests = []

    async def create(self, **kwargs):
        self.requests.append(json.loads(json.dumps(kwargs["messages"], default=str)))
        return self.script.pop(0)


class FakeClient:
    def __init__(self, script):
        self.chat = type("Chat", (), {"completions": FakeCompletions(script)})()


def test_chat_loop_reads_mail_and_defers_send(monkeypatch):
    script = [
        _completion(tool_calls=[("gmail_list_messages", {"query": "from:marcus is:unread"})]),
        _completion(
            tool_calls=[
                (
                    "gmail_send_message",
                    {
                        "to": "marcus.chen@lumacorp.example",
                        "subject": "Re: Project Atlas launch plan",
                        "body": "On track for Friday.",
                        "replyToMessageId": "m05",
                    },
                )
            ]
        ),
        _completion(content="Drafted a reply to Marcus. Confirm to send?"),
    ]
    client = FakeClient(script)
    monkeypatch.setattr(ai_service, "_client", client)
    monkeypatch.setattr(ai_service, "_tool_cache", FAKE_TOOLS)

    box = DemoMailbox.seeded()
    conv = Conversation()
    result = asyncio.run(ai_service.chat_once("reply to marcus", box, conv))

    assert result.reply == "Drafted a reply to Marcus. Confirm to send?"
    assert result.pending_action["tool"] == "gmail_send_message"
    # The list call really ran against the mailbox and its output was fed back.
    second_request = client.chat.completions.requests[1]
    assert second_request[-1]["role"] == "tool"
    assert "ID: m05" in second_request[-1]["content"]
    # The send was only captured, not executed.
    assert "sent-1" not in [m.id for m in box.messages]
    # ...and remembered for the next turn.
    assert conv.pending == result.pending_action
    assert [m["role"] for m in conv.transcript] == ["user", "assistant"]


def test_chat_loop_feeds_tool_errors_back(monkeypatch):
    script = [
        _completion(tool_calls=[("gmail_read_message", {"messageId": "missing"})]),
        _completion(content="I couldn't find that email."),
    ]
    client = FakeClient(script)
    monkeypatch.setattr(ai_service, "_client", client)
    monkeypatch.setattr(ai_service, "_tool_cache", FAKE_TOOLS)

    result = asyncio.run(
        ai_service.chat_once("read it", DemoMailbox.seeded(), Conversation())
    )
    assert result.reply == "I couldn't find that email."
    assert "Error running gmail_read_message" in client.chat.completions.requests[1][-1]["content"]


DRAFT = {
    "to": "marcus.chen@lumacorp.example",
    "subject": "Re: Project Atlas launch plan",
    "body": "On track for Friday.",
    "replyToMessageId": "m05",
}


def _two_turns(monkeypatch, second_message, second_args):
    """Turn 1 drafts DRAFT; turn 2 sends `second_message` and the model
    re-issues the send with `second_args`."""
    script = [
        _completion(tool_calls=[("gmail_send_message", DRAFT)]),
        _completion(content="Draft ready. Send it?"),
        _completion(tool_calls=[("gmail_send_message", second_args)]),
        _completion(content="Done."),
    ]
    client = FakeClient(script)
    monkeypatch.setattr(ai_service, "_client", client)
    monkeypatch.setattr(ai_service, "_tool_cache", FAKE_TOOLS)
    box, conv = DemoMailbox.seeded(), Conversation()
    asyncio.run(ai_service.chat_once("reply to marcus", box, conv))
    result = asyncio.run(ai_service.chat_once(second_message, box, conv))
    sent_ids = [m.id for m in box.messages if m.id.startswith("sent-")]
    return client, conv, result, sent_ids


def test_second_turn_sees_history(monkeypatch):
    client, *_ = _two_turns(monkeypatch, "yes", DRAFT)
    third_request = client.chat.completions.requests[2]
    roles = [m["role"] for m in third_request]
    assert roles[:2] == ["system", "user"] and "tool" in roles
    assert third_request[-1] == {"role": "user", "content": "yes"}


def test_yes_sends_the_exact_draft(monkeypatch):
    _, conv, result, sent_ids = _two_turns(monkeypatch, "Yes, send it", DRAFT)
    assert result.sent and result.pending_action is None
    assert sent_ids == ["sent-1"]
    assert conv.pending is None


def test_changed_draft_is_not_sent(monkeypatch):
    changed = {**DRAFT, "body": "Actually we're slipping a week."}
    _, _, result, sent_ids = _two_turns(monkeypatch, "yes", changed)
    assert not result.sent and sent_ids == []
    assert result.pending_action["args"]["body"] == changed["body"]


def test_non_confirmation_is_not_sent(monkeypatch):
    _, _, result, sent_ids = _two_turns(monkeypatch, "what did marcus ask again?", DRAFT)
    assert not result.sent and sent_ids == []
    assert result.pending_action is not None


def test_trim_keeps_recent_turns_and_shortens_old_tool_output():
    messages = []
    for i in range(12):
        messages += [
            {"role": "user", "content": f"q{i}"},
            {"role": "tool", "tool_call_id": f"c{i}", "content": "x" * 5000},
        ]
    trimmed = _trim(messages)
    users = [m["content"] for m in trimmed if m["role"] == "user"]
    assert users == [f"q{i}" for i in range(4, 12)]
    assert trimmed[0]["role"] == "user"
    tools = [m["content"] for m in trimmed if m["role"] == "tool"]
    assert all(len(t) < 2000 for t in tools[:-1])
    assert len(tools[-1]) == 5000  # current turn untouched
