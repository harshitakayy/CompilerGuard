from harness.analysis import (
    PatternTracker,
    build_feedback,
    category_counts,
    collect_patterns,
    discovery_curve,
    error_pattern,
    normalize_message,
    summarize_patterns,
)
from harness.dedupe import DuplicateTracker, canonical_form
from harness.execution import new_trackers, run_tests


def make(code, expected="FAIL", tid="t"):
    return {"id": tid, "category": "invalid_syntax", "source": "mutation", "code": code,
            "expected_status": expected}


def test_canonical_form_ignores_whitespace_only_differences():
    assert canonical_form("x=1+2;") == canonical_form("x  =\n1 +\t2 ;")
    assert canonical_form("x = 5 5;") != canonical_form("x = 55;")


def test_duplicate_tracker_reports_first_occurrence():
    tracker = DuplicateTracker()
    assert tracker.add("x = 1;", "a") is None
    assert tracker.add("x   =   1;", "b") == "a"
    assert "x=1;" in tracker and len(tracker) == 1


def test_messages_are_normalised_to_patterns():
    assert normalize_message("Variable 'foo' is undefined") == "Variable '<ID>' is undefined"
    assert normalize_message("Unexpected character '@'") == "Unexpected character '<CHAR>'"
    assert normalize_message("Unexpected character '''") == "Unexpected character '<CHAR>'"
    assert normalize_message("Expected RPAREN but got EOF") == "Expected RPAREN but got EOF"


def test_error_pattern_of_pass_is_none_and_raw_keeps_names():
    assert error_pattern({"status": "PASS"}) is None
    resp = {"status": "FAIL", "type": "SEMANTIC_ERROR", "message": "Variable 'q' is undefined"}
    assert error_pattern(resp) == "SEMANTIC_ERROR: Variable '<ID>' is undefined"
    assert error_pattern(resp, normalized=False) == "SEMANTIC_ERROR: Variable 'q' is undefined"


def test_different_variable_names_are_one_pattern():
    results = run_tests([make("x = a;", tid="1"), make("x = b;", tid="2")])
    assert len(collect_patterns(results)) == 1
    assert len(collect_patterns(results, normalized=False)) == 2


def test_summaries_and_discovery_curve():
    results = run_tests([
        make("x = 1;", "PASS", "1"), make("x = ;", tid="2"), make("y = ;", tid="3"),
        make("x = 1", tid="4"), make("x = 1 @", tid="5"),
    ])
    groups = summarize_patterns(results)
    assert groups[0]["count"] == 2 and groups[0]["pattern"].endswith("got SEMICOLON")
    assert category_counts(results) == {"LEXICAL_ERROR": 1, "PASS": 1, "SYNTAX_ERROR": 3}
    assert discovery_curve(results) == [0, 1, 1, 2, 3]


def test_novelty_tracking_flags_only_first_sighting():
    dups, pats = new_trackers()
    results = run_tests([make("x = ;", tid="1"), make("y = ;", tid="2"), make("x = 1", tid="3")], dups, pats)
    assert [r["new_pattern"] for r in results] == [True, False, True]
    assert PatternTracker().observe(None, "x") is False


def test_duplicates_are_tracked_across_results():
    dups, _ = new_trackers()
    results = run_tests([make("x = ;", tid="1"), make("x=;", tid="2")], dups)
    assert results[0]["duplicate_of"] is None and results[1]["duplicate_of"] == "1"


def test_feedback_has_patterns_and_examples():
    results = run_tests([make("x = ;", tid="1"), make("x = 1", tid="2"), make("x = 1;", "PASS", "3")])
    feedback = build_feedback(results)
    assert {p["pattern"] for p in feedback["patterns"]} == collect_patterns(results)
    assert all("code" in e and "message" in e for e in feedback["examples"])
    assert len(feedback["examples"]) <= 8
