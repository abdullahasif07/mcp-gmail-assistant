import httpx2
import openai

from services.ai_service import _clean_schema, _parse_args, friendly_ai_error


def _status_error(cls, status: int, body: dict | None = None):
    response = httpx2.Response(status, request=httpx2.Request("POST", "https://api.openai.com/v1/x"))
    return cls("error", response=response, body=body)


def test_clean_schema_drops_schema_marker_only():
    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "additionalProperties": False,
        "properties": {"q": {"type": "string"}},
    }
    assert _clean_schema(schema) == {
        "type": "object",
        "additionalProperties": False,
        "properties": {"q": {"type": "string"}},
    }


def test_clean_schema_handles_missing_schema():
    assert _clean_schema(None) == {"type": "object", "properties": {}}


def test_parse_args():
    assert _parse_args('{"query": "is:unread"}') == {"query": "is:unread"}
    assert _parse_args("") == {}
    assert _parse_args("not json") is None
    assert _parse_args("[1, 2]") is None


def test_friendly_ai_error_messages():
    rate = _status_error(openai.RateLimitError, 429)
    quota = _status_error(
        openai.RateLimitError, 429, {"code": "insufficient_quota", "message": "x"}
    )
    bad_key = _status_error(openai.AuthenticationError, 401)
    other = _status_error(openai.BadRequestError, 400)
    assert "rate limiting" in (friendly_ai_error(rate) or "")
    assert "out of credits" in (friendly_ai_error(quota) or "")
    assert "API key" in (friendly_ai_error(bad_key) or "")
    assert friendly_ai_error(other) is None
    assert friendly_ai_error(ValueError("x")) is None
