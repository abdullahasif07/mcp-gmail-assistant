"""Drive the full chat tool loop against the demo mailbox with a scripted
fake OpenAI client (no network)."""

import asyncio
import json

from openai.types.chat import ChatCompletion

from services import ai_service
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
    result = asyncio.run(ai_service.chat_once("reply to marcus", box))

    assert result.reply == "Drafted a reply to Marcus. Confirm to send?"
    assert result.pending_action["tool"] == "gmail_send_message"
    # The list call really ran against the mailbox and its output was fed back.
    second_request = client.chat.completions.requests[1]
    assert second_request[-1]["role"] == "tool"
    assert "ID: m05" in second_request[-1]["content"]
    # The send was only captured, not executed.
    assert "sent-1" not in [m.id for m in box.messages]


def test_chat_loop_feeds_tool_errors_back(monkeypatch):
    script = [
        _completion(tool_calls=[("gmail_read_message", {"messageId": "missing"})]),
        _completion(content="I couldn't find that email."),
    ]
    client = FakeClient(script)
    monkeypatch.setattr(ai_service, "_client", client)
    monkeypatch.setattr(ai_service, "_tool_cache", FAKE_TOOLS)

    result = asyncio.run(ai_service.chat_once("read it", DemoMailbox.seeded()))
    assert result.reply == "I couldn't find that email."
    assert "Error running gmail_read_message" in client.chat.completions.requests[1][-1]["content"]
