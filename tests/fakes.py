"""Test doubles: no network access or API credits are ever needed."""

from types import SimpleNamespace

from ai.ai_generator import AIResult


def ok(tests, model="scripted-test-model"):
    return AIResult(status="OK", tests=list(tests), model=model, raw_count=len(tests))


def error(code, reason="scripted failure"):
    return AIResult(status="ERROR", error_code=code, reason=reason, model="scripted-test-model")


class ScriptedAI:
    """Drop-in replacement for ``AIGenerator`` that replays scripted results.

    Each scripted item is an ``AIResult`` or a callable
    ``(feedback, count, previous_tests) -> AIResult``.
    """

    model = "scripted-test-model"

    def __init__(self, script=(), available=True, reason="scripted: unavailable"):
        self.script = list(script)
        self.available = available
        self.reason = reason
        self.calls = []

    def availability(self):
        return (True, None) if self.available else (False, self.reason)

    def is_available(self):
        return self.available

    def generate(self, feedback, count, previous_tests=None):
        previous = list(previous_tests or [])
        self.calls.append({"feedback": feedback, "count": count, "previous": previous})
        if not self.script:
            return error("EMPTY_RESULT", "script exhausted")
        item = self.script.pop(0)
        return item(feedback, count, previous) if callable(item) else item


class FakeOpenAIClient:
    """Mimics ``client.responses.create`` of the OpenAI SDK."""

    def __init__(self, outcome):
        self.outcome = outcome
        self.requests = []
        self.responses = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return SimpleNamespace(
            output_text=self.outcome,
            usage=SimpleNamespace(input_tokens=11, output_tokens=7),
        )
