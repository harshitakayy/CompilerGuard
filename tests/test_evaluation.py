import json
from pathlib import Path

from harness.dedupe import canonical_form
from tests.evaluation import EvaluationConfig, describe, run_evaluation
from tests.fakes import ScriptedAI, error, ok


def cfg(tmp_path, **kw):
    params = dict(budget=12, ai_seed_tests=4, round_size=4, trials=2, base_seed=7,
                  valid_pool=15, output_dir=str(tmp_path))
    params.update(kw)
    return EvaluationConfig(**params)


def fresh_programs(tag):
    """Scripted AI round: unique programs, none repeating anything executed."""
    def build(feedback, count, previous):
        return ok([f"{tag}{i} = {i + 1} +;" for i in range(count)] if tag == "e"
                  else [f"{tag}{i} = {i + 1};" for i in range(count)])
    return build


def full_script(trials):
    # each trial needs two rounds of 4; keep programs globally unique per call
    return [fresh_programs(f"{chr(97 + n)}") for n in range(trials * 2)]


def load(summary, name):
    return json.loads((Path(summary["report_dir"]) / name).read_text(encoding="utf-8"))


def test_without_ai_nothing_is_compared_or_invented(tmp_path):
    summary = run_evaluation(cfg(tmp_path), ScriptedAI(available=False), echo=None)
    assert summary["ai_available"] is False
    assert all(t["status"] == "AI_NOT_RUN" and t["ai_guided"] is None for t in summary["trials"])
    assert summary["aggregate"]["comparison"] is None
    assert summary["aggregate"]["trials_complete"] == 0
    assert summary["aggregate"]["baseline_all_trials"]["tests_executed"]["mean"] == 12
    assert len(summary["aggregate"]["incomplete_trials"]) == 2


def test_complete_trials_use_equal_budgets_and_a_shared_prefix(tmp_path):
    ai = ScriptedAI(full_script(2))
    summary = run_evaluation(cfg(tmp_path), ai, echo=None)
    assert [t["status"] for t in summary["trials"]] == ["COMPLETE", "COMPLETE"]
    for trial in summary["trials"]:
        assert trial["baseline"]["tests_executed"] == trial["ai_guided"]["tests_executed"] == 12
        assert trial["ai_guided"]["seed_tests"] == 4 and trial["ai_guided"]["ai_tests_executed"] == 8

    details = load(summary, "evaluation_details.json")["trials"][0]
    base, aiarm = details["baseline"], details["ai_guided"]
    assert [r["code"] for r in base[:4]] == [r["code"] for r in aiarm[:4]]   # paired prefix
    assert all(r["source"] == "ai" for r in aiarm[4:]) and all(r["source"] == "mutation" for r in aiarm[:4])
    assert len(aiarm) == len(base) == 12


def test_aggregate_reports_mean_and_spread_over_actual_trials(tmp_path):
    summary = run_evaluation(cfg(tmp_path), ScriptedAI(full_script(2)), echo=None)
    agg = summary["aggregate"]
    assert agg["trials_complete"] == 2
    stat = agg["comparison"]["ai_guided"]["unique_error_patterns"]
    assert stat["n"] == 2 and stat["stdev"] is not None
    values = [t["ai_guided"]["unique_error_patterns"] for t in summary["trials"]]
    assert stat["values"] == values
    assert "paired_difference_ai_minus_baseline" in agg["comparison"]


def test_historical_result_is_labelled_unverified(tmp_path):
    summary = run_evaluation(cfg(tmp_path, trials=1), ScriptedAI(available=False), echo=None)
    hist = summary["historical_reference"]
    assert hist["status"] == "historical_reported_unverified"
    assert hist["reported"]["ai_only_error_patterns"] == 6


def test_under_budget_ai_arm_is_incomplete_and_excluded(tmp_path):
    def short(feedback, count, previous):
        return ok([f"s{len(previous)}_{i} = {i};" for i in range(2)])  # only 2 of 4

    summary = run_evaluation(cfg(tmp_path, trials=1, max_extra_rounds=0), ScriptedAI([short, short]), echo=None)
    trial = summary["trials"][0]
    assert trial["status"] == "INCOMPLETE" and trial["ai_guided"]["tests_executed"] < 12
    assert summary["aggregate"]["comparison"] is None
    assert any("executed" in n for n in trial["notes"])


def test_ai_failure_is_reported_as_unavailable_not_counted(tmp_path):
    summary = run_evaluation(cfg(tmp_path, trials=1), ScriptedAI([error("INSUFFICIENT_QUOTA")]), echo=None)
    assert summary["trials"][0]["status"] == "AI_UNAVAILABLE"
    assert summary["aggregate"]["trials_complete"] == 0


def test_ai_duplicates_are_discarded_not_executed(tmp_path):
    def dup_then_new(feedback, count, previous):
        seen = [p for p in previous][:2]  # repeat two executed tests
        fresh = [f"n{len(previous)}_{i} = {i};" for i in range(count)]
        return ok(seen + fresh)

    ai = ScriptedAI([dup_then_new] * 4)
    summary = run_evaluation(cfg(tmp_path, trials=1), ai, echo=None)
    arm = summary["trials"][0]["ai_guided"]
    # AI-generator-side validation already removes duplicates of previous tests.
    details = load(summary, "evaluation_details.json")["trials"][0]["ai_guided"]
    assert len({canonical_form(r["code"]) for r in details}) == len(details)
    assert arm["duplicate_rate"] == 0.0


def test_metrics_cover_required_fields(tmp_path):
    summary = run_evaluation(cfg(tmp_path, trials=1), ScriptedAI(full_script(1)), echo=None)
    arm = summary["trials"][0]["ai_guided"]
    for key in ("tests_executed", "unique_error_patterns", "error_categories", "duplicate_rate",
                "potential_compiler_bugs", "new_patterns_after_seed", "patterns_per_test",
                "discovery_curve", "rounds"):
        assert key in arm, key
    assert len(arm["discovery_curve"]) == 12
    assert summary["trials"][0]["comparison"]["ai_only_patterns"] is not None


def test_describe_statistics():
    assert describe([5])["stdev"] is None and describe([5])["mean"] == 5
    assert describe([1, 3])["mean"] == 2 and round(describe([1, 3])["stdev"], 3) == 1.414
    assert describe([])["n"] == 0
