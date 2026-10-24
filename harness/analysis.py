"""Error-pattern analysis and statistics over executed tests."""

import re
from collections import Counter, OrderedDict

_LEXICAL_RE = re.compile(r"^Unexpected character .*$", re.S)
_UNDEFINED_RE = re.compile(r"^Variable '.*' is undefined$", re.S)


def normalize_message(message):
    """Replace data-dependent parts (character, variable name) with
    placeholders so that equivalent compiler behaviour maps to one pattern."""
    if message is None:
        return "UNKNOWN"
    if _LEXICAL_RE.match(message):
        return "Unexpected character '<CHAR>'"
    if _UNDEFINED_RE.match(message):
        return "Variable '<ID>' is undefined"
    return message


def error_pattern(response, normalized=True):
    """``TYPE: message`` for a failing compiler response, else ``None``."""
    if response.get("status") != "FAIL":
        return None
    message = response.get("message")
    if normalized:
        message = normalize_message(message)
    return f"{response.get('type', 'UNKNOWN')}: {message}"


class PatternTracker:
    """Tracks which error patterns have been seen so far (novelty)."""

    def __init__(self):
        self.seen = OrderedDict()

    def observe(self, pattern, test_id):
        """Return True if ``pattern`` is new."""
        if pattern is None or pattern in self.seen:
            return False
        self.seen[pattern] = test_id
        return True


def collect_patterns(results, normalized=True):
    return {
        p
        for r in results
        if (p := error_pattern(r["compiler_response"], normalized)) is not None
    }


def summarize_patterns(results):
    """Group failures by normalized pattern with counts and an example."""
    groups = OrderedDict()
    for r in results:
        pattern = error_pattern(r["compiler_response"])
        if pattern is None:
            continue
        entry = groups.setdefault(
            pattern,
            {
                "pattern": pattern,
                "type": r["compiler_response"].get("type"),
                "count": 0,
                "example_code": r["code"],
                "first_test_id": r["id"],
            },
        )
        entry["count"] += 1
    return sorted(groups.values(), key=lambda e: (-e["count"], e["pattern"]))


def category_counts(results):
    """Counts of compiler outcomes: PASS or the failure type."""
    counter = Counter()
    for r in results:
        resp = r["compiler_response"]
        counter["PASS" if resp["status"] == "PASS" else resp.get("type", "UNKNOWN")] += 1
    return dict(sorted(counter.items()))


def discovery_curve(results):
    """Cumulative number of unique normalized patterns after each test."""
    seen, curve = set(), []
    for r in results:
        pattern = error_pattern(r["compiler_response"])
        if pattern is not None:
            seen.add(pattern)
        curve.append(len(seen))
    return curve


def candidate_bugs(results):
    return [r for r in results if r.get("potential_compiler_bug")]


def summarize_results(results):
    """Aggregate counters for a list of executed-test records."""
    total = len(results)
    outcomes = Counter(r["outcome"] for r in results)
    return {
        "total": total,
        "outcomes": dict(sorted(outcomes.items())),
        "expectation_matched": sum(1 for r in results if r["expectation_matched"]),
        "expectation_mismatched": sum(1 for r in results if not r["expectation_matched"]),
        "error_type_mismatches": sum(1 for r in results if r.get("error_type_matched") is False),
        "potential_compiler_bugs": len(candidate_bugs(results)),
        "intent_revised_by_oracle": sum(
            1 for r in results if r["adjudication"] == "EXPECTATION_REVISED_BY_ORACLE"
        ),
        "compiler_outcomes": category_counts(results),
        "unique_error_patterns": len(collect_patterns(results)),
        "duplicate_tests": sum(1 for r in results if r.get("duplicate_of")),
    }


def build_feedback(results, previous_patterns=None, max_examples=8):
    """Structured feedback for the AI generator from executed tests."""
    patterns = summarize_patterns(results)
    new_flags = set(previous_patterns or [])
    for entry in patterns:
        entry["new_since_last_round"] = bool(new_flags) and entry["pattern"] not in new_flags

    examples, seen_codes = [], set()
    # Prioritise surprising outcomes, then diverse failures.
    ordered = sorted(
        results,
        key=lambda r: (not r.get("potential_compiler_bug"), r["expectation_matched"]),
    )
    for r in ordered:
        resp = r["compiler_response"]
        if resp["status"] != "FAIL" and r["expectation_matched"]:
            continue
        if r["code"] in seen_codes:
            continue
        seen_codes.add(r["code"])
        examples.append(
            {
                "code": r["code"],
                "status": resp["status"],
                "type": resp.get("type"),
                "line": resp.get("line"),
                "column": resp.get("column"),
                "message": resp.get("message"),
            }
        )
        if len(examples) >= max_examples:
            break
    return {"patterns": patterns, "examples": examples}
