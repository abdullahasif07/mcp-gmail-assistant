from google.genai import errors as genai_errors

from services.gemini_service import _strip_schema_for_gemini, friendly_gemini_error


def test_strip_schema_removes_keys_gemini_rejects():
    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "q": {"type": "string", "default": "is:unread", "title": "Q"},
        },
    }
    assert _strip_schema_for_gemini(schema) == {
        "type": "object",
        "properties": {"q": {"type": "string"}},
    }


def test_strip_schema_handles_missing_schema():
    assert _strip_schema_for_gemini(None) == {"type": "object", "properties": {}}


def test_friendly_gemini_error_maps_rate_limit_and_auth():
    rate_limited = genai_errors.ClientError(429, {"error": {"message": "quota"}})
    bad_key = genai_errors.ClientError(403, {"error": {"message": "denied"}})
    other = genai_errors.ClientError(400, {"error": {"message": "bad"}})
    assert "rate limit" in (friendly_gemini_error(rate_limited) or "")
    assert "API key" in (friendly_gemini_error(bad_key) or "")
    assert friendly_gemini_error(other) is None
    assert friendly_gemini_error(ValueError("x")) is None
