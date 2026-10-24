"""AI-guided test generation for CompilerGuard.

The generator sends the CG-Lang grammar, structured compiler feedback
(grouped error patterns and concrete failing examples) and the list of
already-executed programs to an OpenAI model and asks for NEW test programs
that probe related edge cases.

Design rules:

* Importing this module has no side effects: no client is created, no
  environment is read, no network call is made.
* Credentials come from ``OPENAI_API_KEY`` (environment or a ``.env`` file in
  the project root). The key is never printed, logged or stored; error text is
  redacted before it leaves this module.
* :meth:`AIGenerator.generate` never raises. Missing credentials, a missing
  SDK, network errors, rate limits, exhausted quota, malformed JSON and empty
  results are all reported through :class:`AIResult` so the surrounding
  pipeline can carry on without AI tests.
* Nothing is fabricated: ``tests`` contains only programs returned by the model
  that passed validation.
"""

import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = "gpt-5.4-mini"

GRAMMAR = """\
program     -> statement*
statement   -> IDENTIFIER '=' expression ';'
expression  -> term (('+' | '-') term)*
term        -> factor (('*' | '/') factor)*
factor      -> NUMBER | IDENTIFIER | '(' expression ')'
"""

LANGUAGE_NOTES = """\
- IDENTIFIER is [A-Za-z_][A-Za-z0-9_]*; NUMBER is [0-9]+ (no decimals, no unary minus). ASCII only.
- Whitespace (spaces, tabs, newlines) is insignificant. An empty program is valid.
- A variable may be used only after an earlier statement has assigned it
  (using an undefined variable is a SEMANTIC error; 'x = x + 1;' as the first statement is one too).
- NOT supported: if, else, while, braces, comparison operators (==, !=, <, >, <=, >=), %, ^, strings,
  comments, decimals. They are tokenised or rejected, so they are legitimate edge cases.
- Error classes reported by the compiler: LEXICAL_ERROR (bad character), SYNTAX_ERROR, SEMANTIC_ERROR.
"""

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {"tests": {"type": "array", "items": {"type": "string"}}},
    "required": ["tests"],
    "additionalProperties": False,
}

# Error codes after which a multi-round loop should stop asking the AI.
NON_FATAL_ERROR_CODES = {"BAD_RESPONSE", "EMPTY_RESULT"}

MAX_TEST_LENGTH = 300
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_KEY_RE = re.compile(r"sk-[A-Za-z0-9_\-\*\.]{4,}")
_CANON_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|[0-9]+|==|!=|<=|>=|\S")


def _canonical(code: str) -> str:
    return " ".join(_CANON_RE.findall(code))


@dataclass
class AIResult:
    status: str  # "OK", "SKIPPED" or "ERROR"
    tests: List[str] = field(default_factory=list)
    reason: Optional[str] = None
    error_code: Optional[str] = None
    rejected: List[Dict[str, str]] = field(default_factory=list)
    raw_count: int = 0
    model: Optional[str] = None
    usage: Optional[Dict[str, Any]] = None
    duration_seconds: float = 0.0

    def to_dict(self):
        return asdict(self)


def _load_env():
    """Load ``.env`` from the project root if python-dotenv is installed."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(PROJECT_ROOT / ".env", override=False)


def redact(text: str, api_key: Optional[str] = None) -> str:
    text = str(text)
    if api_key:
        text = text.replace(api_key, "[REDACTED]")
    return _KEY_RE.sub("[REDACTED]", text)


def validate_ai_tests(
    raw: Any,
    count: int,
    previous_tests: Optional[List[str]] = None,
) -> Tuple[List[str], List[Dict[str, str]]]:
    """Validate model output; return ``(accepted, rejected)``.

    Accepted programs are non-empty strings of bounded length without control
    characters, unique (whitespace-insensitively) within the batch and against
    ``previous_tests``. At most ``count`` programs are accepted.
    """
    accepted: List[str] = []
    rejected: List[Dict[str, str]] = []
    if not isinstance(raw, list):
        return accepted, [{"code": repr(raw)[:80], "reason": "response is not a list"}]

    seen = {_canonical(p) for p in (previous_tests or [])}
    for item in raw:
        if not isinstance(item, str):
            rejected.append({"code": repr(item)[:80], "reason": "not a string"})
            continue
        code = item.strip()
        if not code:
            rejected.append({"code": item[:80], "reason": "empty"})
        elif len(code) > MAX_TEST_LENGTH:
            rejected.append({"code": code[:80], "reason": "too long"})
        elif _CONTROL_RE.search(code):
            rejected.append({"code": code[:80], "reason": "control characters"})
        elif _canonical(code) in seen:
            rejected.append({"code": code[:80], "reason": "duplicate"})
        elif len(accepted) >= count:
            rejected.append({"code": code[:80], "reason": "over requested count"})
        else:
            seen.add(_canonical(code))
            accepted.append(code)
    return accepted, rejected


def parse_response_text(text: str) -> Any:
    """Parse the model's JSON. Accepts ``{"tests": [...]}`` or a bare list,
    tolerating a surrounding Markdown code fence."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", cleaned).strip()
    data = json.loads(cleaned)
    if isinstance(data, dict):
        data = data.get("tests")
    return data


def feedback_from_failures(failures: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Convert a plain list of ``{code, type, message}`` failures into the
    structured feedback format."""
    patterns: Dict[str, Dict[str, Any]] = {}
    for f in failures:
        key = f"{f.get('type')}: {f.get('message')}"
        entry = patterns.setdefault(
            key, {"pattern": key, "type": f.get("type"), "count": 0, "example_code": f.get("code")}
        )
        entry["count"] += 1
    return {"patterns": list(patterns.values()), "examples": list(failures)[:8]}


def build_prompt(feedback: Dict[str, Any], count: int, previous_tests: List[str], grammar: str = GRAMMAR, notes: str = LANGUAGE_NOTES, language: str = "CG-Lang") -> str:
    patterns = json.dumps(feedback.get("patterns", [])[:10], indent=2, ensure_ascii=False)
    examples = json.dumps(feedback.get("examples", [])[:3], indent=2, ensure_ascii=False)
    previous = json.dumps(previous_tests[-15:], ensure_ascii=False)
    return f"""You are a compiler test generator for the language '{language}'.

Grammar (EBNF; quoted items are terminals, ID/NUMBER/STRING/CHAR are token classes):
{grammar}
Language notes:
{notes}
Compiler feedback from tests that were already executed.

Error patterns observed (grouped; 'count' is how often each occurred):
{patterns}

Concrete examples with the structured compiler response:
{examples}

Programs already executed (do NOT repeat these or whitespace-only variants):
{previous}

Task: write {count} NEW complete {language} test programs that explore edge cases related to the
observed error patterns and, where possible, reach error patterns that are NOT yet in the list
(for example other token types appearing in unexpected positions, nesting, statement boundaries,
undefined-variable ordering). Mix invalid and valid programs. Keep each program under 200
characters. Use only characters you intend to test.

Output rules: return ONLY a JSON object of the form {{"tests": ["program 1", "program 2", ...]}}
with exactly {count} strings, no explanations.
"""


class AIGenerator:
    """Wrapper around the OpenAI Responses API with graceful degradation."""

    def __init__(
        self,
        client: Any = None,
        model: Optional[str] = None,
        timeout: float = 60.0,
        max_retries: int = 2,
        grammar: Optional[str] = None,
        notes: Optional[str] = None,
        language: str = "CG-Lang",
        api_key: Optional[str] = None,
    ):
        _load_env()
        self._client = client
        self._explicit_key = api_key or None  # held in memory only, never logged
        self.grammar = grammar or GRAMMAR
        self.notes = notes or LANGUAGE_NOTES
        self.language = language
        self.model = model or os.getenv("CG_GROQ_MODEL") or "openai/gpt-oss-20b"
        self.timeout = timeout
        self.max_retries = max_retries

    # -- availability --------------------------------------------------
    @property
    def _api_key(self) -> Optional[str]:
        return self._explicit_key or os.getenv("GROQ_API_KEY") or None

    def availability(self) -> Tuple[bool, Optional[str]]:
        """Return ``(available, reason_if_not)`` without touching the network."""
        if self._client is not None:
            return True, None
        if not self._api_key:
            return False, "GROQ_API_KEY is not set (environment or .env)"
        try:
            import openai  # noqa: F401
        except ImportError:
            return False, "the 'openai' package is not installed"
        return True, None

    def is_available(self) -> bool:
        return self.availability()[0]

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=self._api_key,  base_url="https://api.groq.com/openai/v1", timeout=self.timeout, max_retries=self.max_retries
            )
        return self._client

    # -- generation ----------------------------------------------------
    def generate(
        self,
        feedback: Dict[str, Any],
        count: int,
        previous_tests: Optional[List[str]] = None,
    ) -> AIResult:
        started = time.monotonic()
        available, reason = self.availability()
        if not available:
            return AIResult(status="SKIPPED", reason=reason, model=self.model)

        previous = list(previous_tests or [])
        prompt = build_prompt(feedback, count, previous, self.grammar, self.notes, self.language)
        try:
            response = self._get_client().chat.completions.create(
                model=self.model,
    messages=[
        {
            "role": "system",
            "content": (
    "You generate compiler test programs for CG-Lang. "
    "Return a single valid JSON object, with no Markdown or "
    "explanations, using exactly this structure: "
    '{"tests": ["program 1", "program 2"]}. '
    "The tests field must contain an array of strings. "
    "Generate only complete test programs."
),
        },
        {"role": "user", "content": prompt},
    ],
    max_tokens=1500,
    response_format={"type": "json_object"},
            )
        except Exception as exc:  # noqa: BLE001 - never crash the pipeline
            code, message = self._classify_exception(exc)
            return AIResult(
                status="ERROR",
                error_code=code,
                reason=message,
                model=self.model,
                duration_seconds=round(time.monotonic() - started, 3),
            )

        usage = self._usage(response)
        text = response.choices[0].message.content
        if not isinstance(text, str) or not text.strip():
            return AIResult(
                status="ERROR",
                error_code="BAD_RESPONSE",
                reason="the model returned no text (response may be incomplete)",
                model=self.model,
                usage=usage,
                duration_seconds=round(time.monotonic() - started, 3),
            )
        try:
            raw = parse_response_text(text)
        except (json.JSONDecodeError, ValueError):
            return AIResult(
                status="ERROR",
                error_code="BAD_RESPONSE",
                reason="the model returned invalid JSON",
                model=self.model,
                usage=usage,
                duration_seconds=round(time.monotonic() - started, 3),
            )

        accepted, rejected = validate_ai_tests(raw, count, previous)
        raw_count = len(raw) if isinstance(raw, list) else 0
        if not accepted:
            return AIResult(
                status="ERROR",
                error_code="EMPTY_RESULT",
                reason="no valid, non-duplicate tests in the response",
                rejected=rejected,
                raw_count=raw_count,
                model=self.model,
                usage=usage,
                duration_seconds=round(time.monotonic() - started, 3),
            )
        return AIResult(
            status="OK",
            tests=accepted,
            rejected=rejected,
            raw_count=raw_count,
            model=self.model,
            usage=usage,
            duration_seconds=round(time.monotonic() - started, 3),
        )

    # -- helpers -------------------------------------------------------
    @staticmethod
    def _usage(response) -> Optional[Dict[str, Any]]:
        usage = getattr(response, "usage", None)
        if usage is None:
            return None
        return {
            "input_tokens": getattr(usage, "input_tokens", None),
            "output_tokens": getattr(usage, "output_tokens", None),
        }

    def _classify_exception(self, exc: Exception) -> Tuple[str, str]:
        key = self._api_key
        try:
            import openai
        except ImportError:  # pragma: no cover - client injected without SDK
            return "UNEXPECTED_ERROR", redact(f"{type(exc).__name__}: {exc}", key)

        text = redact(f"{type(exc).__name__}: {exc}", key)
        if isinstance(exc, (openai.AuthenticationError, openai.PermissionDeniedError)):
            return "AUTH_ERROR", "authentication failed (check GROQ_API_KEY)"
        if isinstance(exc, openai.RateLimitError):
            if getattr(exc, "code", None) == "insufficient_quota" or "insufficient_quota" in str(exc):
                return "INSUFFICIENT_QUOTA", "API quota/credits exhausted"
            return "RATE_LIMITED", "rate limited by the API"
        if isinstance(exc, openai.APITimeoutError):
            return "TIMEOUT", "the request timed out"
        if isinstance(exc, openai.APIConnectionError):
            return "CONNECTION_ERROR", "could not connect to the API"
        if isinstance(exc, openai.BadRequestError):
            return "BAD_REQUEST", text
        if isinstance(exc, openai.APIStatusError):
            return f"API_ERROR_{getattr(exc, 'status_code', 'UNKNOWN')}", text
        return "UNEXPECTED_ERROR", text


def generate_targeted_tests(failures, count=5, previous_tests=None):
    """Backward-compatible helper: returns a list of test programs, or an
    empty list when AI generation is unavailable or fails."""
    feedback = failures if isinstance(failures, dict) else feedback_from_failures(failures)
    return AIGenerator().generate(feedback, count, previous_tests).tests


if __name__ == "__main__":
    generator = AIGenerator()
    ok, why = generator.availability()
    print("AI available:", ok, "" if ok else f"({why})")
    if ok:
        demo = [
            {"code": "x = + 10;", "type": "SYNTAX_ERROR", "message": "Expected expression but got PLUS"},
            {"code": "x = (10 + 5;", "type": "SYNTAX_ERROR", "message": "Expected RPAREN but got SEMICOLON"},
        ]
        result = generator.generate(feedback_from_failures(demo), 5)
        print(result.status, result.reason or "")
        for i, test in enumerate(result.tests, 1):
            print(f"{i}. {test!r}")
