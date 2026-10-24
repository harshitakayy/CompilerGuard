import json
from pathlib import Path

import pytest

import harness.execution as execution
from harness.execution import run_test
from harness.reporting import DEFAULT_REPORTS_DIR, PROJECT_ROOT
from tests.fakes import ScriptedAI, error, ok
from tests.test_runner import PipelineConfig, main, run_pipeline


def config(tmp_path, **overrides):
    params = dict(seed=42, valid_count=8, mutation_count=12, ai_rounds=3, ai_per_round=3,
                  output_dir=str(tmp_path))
    params.update(overrides)
    return PipelineConfig(**params)


def load(summary, name):
    return json.loads((Path(summary["report_dir"]) / name).read_text(encoding="utf-8"))


ROUND1 = ["x = 1;\ny = x +;", "q = (1;", "a = b;"]
ROUND2 = ["x = 1;\ny = x * (2 - 1);", "w = 1 @ 2;", "x = ;"]


# -- no AI --------------------------------------------------------------------
def test_pipeline_completes_without_ai_and_reports_skip(tmp_path):
    summary = run_pipeline(config(tmp_path), ScriptedAI(available=False), echo=None)
    assert summary["ai_status"] == "SKIPPED" and summary["totals"]["ai"] == 0
    assert summary["valid_accepted"] == 8 and summary["mutants_rejected"] == 12
    ai_report = load(summary, "ai_results.json")
    assert ai_report["results"] == [] and ai_report["ai"]["status"] == "SKIPPED"
    assert "unavailable" in ai_report["ai"]["reason"]


def test_no_ai_flag(tmp_path):
    summary = run_pipeline(config(tmp_path, ai_enabled=False), ScriptedAI(), echo=None)
    assert summary["ai_status"] == "SKIPPED"


def test_cli_runs_without_api_key(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    import ai.ai_generator as ai_module

    monkeypatch.setattr(ai_module, "_load_env", lambda: None)
    assert main(["--output-dir", str(tmp_path), "--valid", "5", "--mutations", "8"]) == 0
    out = capsys.readouterr().out
    assert "AI generation SKIPPED" in out and "FINAL STATISTICS" in out


# -- with (scripted) AI ---------------------------------------------------------
def test_ai_feedback_loop_executes_labelled_ai_tests(tmp_path):
    ai = ScriptedAI([ok(ROUND1), ok(ROUND2)])
    summary = run_pipeline(config(tmp_path, ai_rounds=2), ai, echo=None)

    assert summary["ai_status"] == "COMPLETED" and summary["totals"]["ai"] == 6
    results = load(summary, "ai_results.json")["results"]
    assert all(r["source"] == "ai" and r["category"] == "ai_guided" for r in results)
    assert all(r["expected_basis"] == "oracle" for r in results)
    assert results[0]["provenance"]["model"] == "scripted-test-model"
    assert [r["code"] for r in results[:3]] == ROUND1

    # Round 2 received structured compiler feedback and the earlier AI tests.
    second = ai.calls[1]
    assert second["feedback"]["patterns"], "no error patterns forwarded"
    assert all(r in second["previous"] for r in ROUND1)
    assert ai.calls[0]["count"] == 3


def test_ai_duplicates_of_executed_tests_are_discarded(tmp_path):
    def echo_parent(feedback, count, previous):
        return ok([previous[0], "z = 1 +;"])  # first item repeats an existing test

    summary = run_pipeline(config(tmp_path, ai_rounds=1), ScriptedAI([echo_parent]), echo=None)
    report = load(summary, "ai_results.json")
    assert report["summary"]["total"] == 1
    assert report["ai"]["rounds"][0]["duplicates_discarded"] == 1


def test_ai_failure_mid_run_does_not_crash_pipeline(tmp_path):
    ai = ScriptedAI([ok(ROUND1), error("RATE_LIMITED", "rate limited by the API")])
    summary = run_pipeline(config(tmp_path), ai, echo=None)
    assert summary["ai_status"] == "PARTIAL" and summary["totals"]["ai"] == 3
    assert summary["ai_rounds_completed"] == 1
    assert (Path(summary["report_dir"]) / "experiment_metadata.json").exists()


def test_first_round_failure_marks_ai_failed(tmp_path):
    summary = run_pipeline(config(tmp_path), ScriptedAI([error("AUTH_ERROR")]), echo=None)
    assert summary["ai_status"] == "FAILED" and summary["totals"]["ai"] == 0


def test_non_fatal_ai_errors_allow_further_rounds(tmp_path):
    ai = ScriptedAI([error("BAD_RESPONSE"), ok(ROUND1)])
    summary = run_pipeline(config(tmp_path), ai, echo=None)
    assert summary["totals"]["ai"] == 3 and summary["ai_status"] == "PARTIAL"


# -- reports, reproducibility, safety ---------------------------------------------
def test_reports_exist_with_documented_schema(tmp_path):
    summary = run_pipeline(config(tmp_path), ScriptedAI([ok(ROUND1)]), echo=None)
    folder = Path(summary["report_dir"])
    for name in ("valid_results.json", "invalid_results.json", "ai_results.json",
                 "error_statistics.json", "experiment_metadata.json", "pipeline_summary.json"):
        assert (folder / name).exists(), name

    record = load(summary, "invalid_results.json")["results"][0]
    for key in ("id", "category", "source", "code", "expected_status", "actual_status",
                "compiler_response", "oracle", "outcome", "adjudication",
                "potential_compiler_bug", "error_pattern", "provenance"):
        assert key in record, key

    meta = load(summary, "experiment_metadata.json")
    assert meta["config"]["seed"] == 42 and meta["ai"]["status"] in ("COMPLETED", "PARTIAL", "FAILED", "SKIPPED")
    assert {"started_utc", "finished_utc", "environment"} <= set(meta)
    assert load(summary, "error_statistics.json")["error_patterns"]


def test_same_seed_reproduces_the_non_ai_tests(tmp_path):
    codes = []
    for sub in ("a", "b"):
        s = run_pipeline(config(tmp_path / sub, ai_enabled=False), ScriptedAI(), echo=None)
        codes.append([r["code"] for name in ("valid_results.json", "invalid_results.json")
                      for r in load(s, name)["results"]])
    assert codes[0] == codes[1]


def test_runs_never_overwrite_each_other(tmp_path):
    first = run_pipeline(config(tmp_path, ai_enabled=False), ScriptedAI(), echo=None)
    second = run_pipeline(config(tmp_path, ai_enabled=False), ScriptedAI(), echo=None)
    assert first["report_dir"] != second["report_dir"]
    assert Path(first["report_dir"], "valid_results.json").exists()


def test_default_report_location_is_independent_of_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert DEFAULT_REPORTS_DIR == PROJECT_ROOT / "reports" / "runs" and DEFAULT_REPORTS_DIR.is_absolute()


# -- classification of surprising results -----------------------------------------------
def test_equivalent_mutant_is_not_reported_as_compiler_bug():
    record = run_test({"id": "m", "category": "invalid_syntax", "source": "mutation",
                       "code": "x = 1;", "expected_status": "FAIL"})
    assert record["outcome"] == "UNEXPECTED_ACCEPT"
    assert record["adjudication"] == "EXPECTATION_REVISED_BY_ORACLE"
    assert record["potential_compiler_bug"] is False


def test_correct_rejection_is_not_a_failure():
    record = run_test({"id": "m", "category": "invalid_syntax", "source": "mutation",
                       "code": "x = + 1;", "expected_status": "FAIL", "expected_error_type": "SYNTAX_ERROR"})
    assert record["outcome"] == "CORRECT_REJECT" and record["error_type_matched"] is True
    assert record["adjudication"] == "CONSISTENT"


def test_invalid_program_accepted_by_a_faulty_compiler_is_a_candidate_bug(monkeypatch):
    monkeypatch.setattr(execution, "compile_code", lambda code: {"status": "PASS"})
    record = run_test({"id": "m", "category": "invalid_syntax", "source": "mutation",
                       "code": "x = + 1;", "expected_status": "FAIL"})
    assert record["outcome"] == "UNEXPECTED_ACCEPT"
    assert record["potential_compiler_bug"] and record["bug_reasons"] == ["STATUS_MISMATCH"]
    assert record["adjudication"] == "POTENTIAL_COMPILER_BUG"


def test_valid_program_rejected_by_a_faulty_compiler_is_flagged(monkeypatch):
    monkeypatch.setattr(execution, "compile_code", lambda code: {
        "status": "FAIL", "type": "SYNTAX_ERROR", "line": 1, "column": 1, "message": "nope"})
    record = run_test({"id": "v", "category": "valid", "source": "grammar_generator",
                       "code": "x = 1;", "expected_status": "PASS"})
    assert record["outcome"] == "UNEXPECTED_REJECT" and record["potential_compiler_bug"]


def test_internal_compiler_error_is_always_a_candidate(monkeypatch):
    monkeypatch.setattr(execution, "compile_code", lambda code: {
        "status": "FAIL", "type": "INTERNAL_ERROR", "line": None, "column": None, "message": "boom"})
    record = run_test({"id": "m", "category": "invalid_syntax", "source": "mutation",
                       "code": "x = + 1;", "expected_status": "FAIL"})
    assert "INTERNAL_ERROR" in record["bug_reasons"]


def test_strict_mode_exit_code(tmp_path, monkeypatch):
    monkeypatch.setattr(execution, "compile_code", lambda code: {"status": "PASS"})
    import ai.ai_generator as ai_module

    monkeypatch.setattr(ai_module, "_load_env", lambda: None)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert main(["--no-ai", "--strict", "--output-dir", str(tmp_path), "--valid", "4", "--mutations", "6"]) == 1
