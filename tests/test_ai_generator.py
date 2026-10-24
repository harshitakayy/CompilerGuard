import json
from types import SimpleNamespace

import openai
import pytest

import ai.ai_generator as ai_module
from ai.ai_generator import (
    AIGenerator,
    generate_targeted_tests,
    parse_response_text,
    redact,
    validate_ai_tests,
)
from tests.fakes import FakeOpenAIClient

FEEDBACK = {
    "patterns": [{"pattern": "SYNTAX_ERROR: Expected RPAREN but got SEMICOLON", "count": 2,
                  "example_code": "x = (1;"}],
    "examples": [{"code": "x = (1;", "type": "SYNTAX_ERROR", "message": "Expected RPAREN but got SEMICOLON"}],
}
# Plain stand-ins for the HTTP request/response objects: the tests then do not
# depend on which HTTP library (httpx / httpx2) the installed SDK version uses.
REQUEST = SimpleNamespace(method="POST", url="https://api.openai.com/v1/responses")


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    monkeypatch.setattr(ai_module, "_load_env", lambda: None)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def reply(*tests):
    return json.dumps({"tests": list(tests)})


# -- availability -----------------------------------------------------------
def test_module_import_has_no_client_side_effect():
    assert not hasattr(ai_module, "client")


def test_without_key_generation_is_skipped_not_fatal():
    generator = AIGenerator()
    assert generator.availability()[0] is False
    result = generator.generate(FEEDBACK, 5)
    assert result.status == "SKIPPED" and result.tests == [] and "OPENAI_API_KEY" in result.reason


def test_backward_compatible_helper_returns_empty_list_without_key():
    assert generate_targeted_tests([{"code": "x = ;", "type": "SYNTAX_ERROR", "message": "m"}], 3) == []


def test_key_present_means_available(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-1234567890")
    assert AIGenerator().availability() == (True, None)


# -- successful generation ---------------------------------------------------
def test_successful_generation_validates_and_sends_context():
    client = FakeOpenAIClient(reply("x = ((1);", "y = + 2;", "x = (1;"))
    result = AIGenerator(client=client, model="m-test").generate(FEEDBACK, 5, previous_tests=["x = (1;"])
    assert result.status == "OK"
    assert result.tests == ["x = ((1);", "y = + 2;"]  # duplicate of a previous test dropped
    assert result.rejected[0]["reason"] == "duplicate"
    assert result.usage == {"input_tokens": 11, "output_tokens": 7}

    request = client.requests[0]
    assert request["model"] == "m-test" and request["store"] is False
    assert request["text"]["format"]["type"] == "json_schema" and request["text"]["format"]["strict"] is True
    prompt = request["input"]
    assert "statement   -> IDENTIFIER" in prompt                      # grammar
    assert "Expected RPAREN but got SEMICOLON" in prompt              # observed errors
    assert "x = (1;" in prompt                                         # previous tests
    assert "exactly 5 strings" in prompt                               # format and count constraint


def test_bare_json_list_and_code_fences_are_tolerated():
    for text in ('["a = 1;", "b = 2;"]', '```json\n{"tests": ["a = 1;", "b = 2;"]}\n```'):
        result = AIGenerator(client=FakeOpenAIClient(text)).generate(FEEDBACK, 5)
        assert result.status == "OK" and len(result.tests) == 2


def test_count_is_enforced():
    result = AIGenerator(client=FakeOpenAIClient(reply("a = 1;", "b = 2;", "c = 3;"))).generate(FEEDBACK, 2)
    assert len(result.tests) == 2 and result.rejected[0]["reason"] == "over requested count"


# -- bad responses -----------------------------------------------------------
@pytest.mark.parametrize(
    "text,code",
    [
        ("this is not json", "BAD_RESPONSE"),
        ("", "BAD_RESPONSE"),
        (json.dumps({"tests": "x = 1;"}), "EMPTY_RESULT"),
        (json.dumps({"tests": []}), "EMPTY_RESULT"),
        (json.dumps({"tests": [1, None, ""]}), "EMPTY_RESULT"),
        (json.dumps({"other": 1}), "EMPTY_RESULT"),
    ],
)
def test_bad_model_output_is_reported_not_raised(text, code):
    result = AIGenerator(client=FakeOpenAIClient(text)).generate(FEEDBACK, 3)
    assert result.status == "ERROR" and result.error_code == code and result.tests == []


# -- service failures --------------------------------------------------------
def _status_error(cls, status, body=None):
    response = SimpleNamespace(request=REQUEST, status_code=status, headers={})
    return cls("service said no", response=response, body=body)


@pytest.mark.parametrize(
    "exception,code",
    [
        (_status_error(openai.RateLimitError, 429, {"code": "rate_limit_exceeded"}), "RATE_LIMITED"),
        (_status_error(openai.RateLimitError, 429, {"code": "insufficient_quota"}), "INSUFFICIENT_QUOTA"),
        (_status_error(openai.AuthenticationError, 401), "AUTH_ERROR"),
        (openai.APIConnectionError(request=REQUEST), "CONNECTION_ERROR"),
        (openai.APITimeoutError(request=REQUEST), "TIMEOUT"),
        (_status_error(openai.InternalServerError, 500), "API_ERROR_500"),
        (RuntimeError("something odd"), "UNEXPECTED_ERROR"),
    ],
)
def test_service_failures_become_structured_errors(exception, code):
    result = AIGenerator(client=FakeOpenAIClient(exception)).generate(FEEDBACK, 3)
    assert result.status == "ERROR" and result.error_code == code and result.tests == []


def test_api_key_never_appears_in_results(monkeypatch):
    secret = "sk-proj-SECRETKEYVALUE1234567890"
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    client = FakeOpenAIClient(RuntimeError(f"Incorrect API key provided: {secret}"))
    result = AIGenerator(client=client).generate(FEEDBACK, 3)
    assert secret not in json.dumps(result.to_dict()) and "[REDACTED]" in result.reason
    assert secret not in redact(f"key={secret}", secret)
    assert "sk-abcd1234" not in redact("provided: sk-abcd1234****wxyz")


# -- validation ---------------------------------------------------------------
def test_validation_rules():
    accepted, rejected = validate_ai_tests(
        ["ok = 1;", "ok=1;", "", "   ", 7, "x" * 400, "a = 1;\x00", "fine = 2;"], 10, []
    )
    assert accepted == ["ok = 1;", "fine = 2;"]
    assert {r["reason"] for r in rejected} == {"duplicate", "empty", "not a string", "too long", "control characters"}
    assert validate_ai_tests("nope", 3, [])[0] == []


def test_parse_response_text_variants():
    assert parse_response_text('{"tests": ["a"]}') == ["a"]
    assert parse_response_text('["a"]') == ["a"]
    with pytest.raises(ValueError):
        parse_response_text("{broken")
