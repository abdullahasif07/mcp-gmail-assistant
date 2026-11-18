from routes.emails import _parse_list_blob, _parse_read_message

LIST_BLOB = """ID: 18f1
Thread: 18f0
From: Alice <alice@example.com>
Subject: Re: Lunch: today?
Date: Mon, 14 Apr 2026 09:32:00 +0000

---

ID: 18f2
Thread: 18f2
From: bob@example.com
Subject: Hello
Date: Tue, 15 Apr 2026 10:00:00 +0000"""


def test_parse_list_blob_splits_messages_and_keeps_colons_in_values():
    emails = _parse_list_blob(LIST_BLOB)
    assert [e.id for e in emails] == ["18f1", "18f2"]
    assert emails[0].threadId == "18f0"
    assert emails[0].sender == "Alice <alice@example.com>"
    assert emails[0].subject == "Re: Lunch: today?"
    assert emails[1].date == "Tue, 15 Apr 2026 10:00:00 +0000"


def test_parse_list_blob_serializes_sender_as_from():
    (first, _) = _parse_list_blob(LIST_BLOB)
    assert first.model_dump(by_alias=True)["from"] == "Alice <alice@example.com>"


def test_parse_list_blob_handles_empty_results():
    assert _parse_list_blob("") == []
    assert _parse_list_blob("No emails found.") == []


def test_parse_read_message_separates_headers_from_body():
    blob = (
        "From: Alice <alice@example.com>\n"
        "Date: Mon, 14 Apr 2026 09:32:00 +0000\n"
        "Subject: Hello\n"
        "Thread: 18f0\n"
        "\n"
        "Body:\n"
        "Hi there,\n"
        "Subject: this line is body text, not a header\n"
        "\n"
        "Thanks"
    )
    email = _parse_read_message(blob, "18f1")
    assert email.id == "18f1"
    assert email.threadId == "18f0"
    assert email.subject == "Hello"
    assert email.body == (
        "Hi there,\nSubject: this line is body text, not a header\n\nThanks"
    )


def test_parse_read_message_defaults_missing_headers():
    email = _parse_read_message("Body:\nonly a body", "x")
    assert email.sender == "Unknown"
    assert email.subject == "(no subject)"
    assert email.body == "only a body"
