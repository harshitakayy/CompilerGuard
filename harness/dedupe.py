"""Duplicate detection for test programs."""

import re

_CANONICAL_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|[0-9]+|==|!=|<=|>=|\S")


def canonical_form(code):
    """Whitespace-insensitive token form: programs that differ only in
    whitespace are considered the same test."""
    return " ".join(_CANONICAL_RE.findall(code))


class DuplicateTracker:
    """Remembers every program seen and which test id introduced it."""

    def __init__(self):
        self._first_seen = {}

    def __len__(self):
        return len(self._first_seen)

    def __contains__(self, code):
        return canonical_form(code) in self._first_seen

    def add(self, code, test_id=None):
        """Register ``code``; return the id of the first equal test, or
        ``None`` if the program is new."""
        key = canonical_form(code)
        if key in self._first_seen:
            return self._first_seen[key] or "<unknown>"
        self._first_seen[key] = test_id
        return None

    def keys(self):
        return set(self._first_seen)
