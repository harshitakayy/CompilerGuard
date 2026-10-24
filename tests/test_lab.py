import json

import pytest

from lab.experiment import AdaptiveSelector, LabConfig, aggregate, run_lab
from lab.metrics import ArmTracker, ast_shape
from lab.targets import GrammarTarget, get_preset
from harness.execution import run_test
from tests.fakes import ScriptedAI, error, ok

CALC = "expr -> term (('+'|'-') term)*\nterm -> factor (('*'|'/') factor)*\nfactor -> NUMBER | ID | '(' expr ')'\n"


def small(**kw):
    p = dict(budget=24, seed_tests=8, batch=8, trials=2, seed=11, parents=15)
    p.update(kw)
    return LabConfig(**p)


def fresh_ai(feedback, count, previous):
    n = len(previous)
    return ok([f"{1 + n + i} + * {i}" if i % 2 else f"{n + i} + ( {i}" for i in range(count)])


def test_all_requested_metrics_are_reported_per_arm():
    res = run_lab(get_preset("calc"), small(arms=("blind", "feedback")))
    s = res["trials"][0]["arms"]["blind"]["summary"]
    assert s["tests"] == 24 and s["unique_error_patterns"] > 3 and s["bug_signals"] == 0
    assert 0 < s["production_coverage"]["percent"] <= 100 and s["production_coverage"]["total"] == len(get_preset("calc").grammar.alts)
    assert s["ast"]["unique_shapes"] >= 1 and s["ast"]["unique_edges"] >= 1 and s["ast"]["accepted_programs"] >= 1
    assert s["path_coverage"]["available"] and 0 < s["path_coverage"]["percent"] <= 100
    assert len(s["novelty"]) == 24 and sum(v[0] for v in s["novelty"]) == s["novel_tests"] == s["unique_error_patterns"]
    assert s["curves"]["patterns"] == sorted(s["curves"]["patterns"]) and len(s["curves"]["patterns"]) == 24
    assert s["new_patterns_per_test"] == pytest.approx(s["unique_error_patterns"] / 24, abs=1e-3)


def test_equal_budget_and_shared_prefix_across_arms():
    res = run_lab(get_preset("calc"), small(), ScriptedAI([fresh_ai] * 6))
    for trial in res["trials"]:
        arms = trial["arms"]
        assert {k: a["status"] for k, a in arms.items()} == {"blind": "COMPLETE", "feedback": "COMPLETE", "ai": "COMPLETE"}
        assert all(a["summary"]["tests"] == 24 for a in arms.values())
        prefix = lambda k: [t["code"] for t in arms[k]["tests"][:8]]
        assert prefix("blind") == prefix("feedback") == prefix("ai")
        assert all(t["source"] == "ai" for t in arms["ai"]["tests"][8:]) and all(t["source"] == "mutation" for t in arms["feedback"]["tests"])
        for a in arms.values():
            codes = [t["code"] for t in a["tests"]]
            assert len(codes) == len(set(codes))


def test_ai_arm_is_reported_as_not_run_without_credentials_and_never_invented():
    for ai in (None, ScriptedAI(available=False, reason="no key")):
        res = run_lab(get_preset("calc"), small(trials=1), ai)
        arm = res["trials"][0]["arms"]["ai"]
        assert arm["status"] == "NOT_RUN" and arm["summary"] is None and arm["tests"] == []
        assert res["aggregate"]["ai"]["metrics"] is None and res["aggregate"]["blind"]["metrics"]


def test_ai_failures_and_underfill_are_reported_not_counted():
    failed = run_lab(get_preset("calc"), small(trials=1), ScriptedAI([error("INSUFFICIENT_QUOTA", "credits exhausted")]))
    assert failed["trials"][0]["arms"]["ai"]["status"] == "NOT_RUN" and "credits" in failed["trials"][0]["arms"]["ai"]["reason"]
    short = run_lab(get_preset("calc"), small(trials=1, ai_extra_rounds=0), ScriptedAI([ok(["1 + + 2"]), ok(["3 + + 4"]), ok(["5 + + 6"])]))
    assert short["trials"][0]["arms"]["ai"]["status"] == "INCOMPLETE" and short["aggregate"]["ai"]["metrics"] is None


def test_ai_receives_the_custom_grammar_context_and_feedback():
    ai = ScriptedAI([fresh_ai] * 3)
    run_lab(get_preset("calc"), small(trials=1), ai)
    first = ai.calls[0]
    assert first["feedback"]["patterns"] and first["count"] == 8 and len(first["previous"]) >= 8


def test_ai_prompt_carries_the_users_grammar():
    from ai.ai_generator import AIGenerator
    from tests.fakes import FakeOpenAIClient

    client = FakeOpenAIClient(json.dumps({"tests": ["[ a ]"]}))
    g = AIGenerator(client=client, grammar="list -> '[' ID ']'", language="My list language", notes="- tiny")
    assert g.generate({"patterns": [], "examples": []}, 1).status == "OK"
    prompt = client.requests[0]["input"]
    assert "list -> '[' ID ']'" in prompt and "My list language" in prompt and "- tiny" in prompt


def test_experiment_is_deterministic_for_the_non_ai_arms():
    a = run_lab(get_preset("cpp"), small(trials=1, arms=("blind", "feedback")))
    b = run_lab(get_preset("cpp"), small(trials=1, arms=("blind", "feedback")))
    codes = lambda r, k: [t["code"] for t in r["trials"][0]["arms"][k]["tests"]]
    assert codes(a, "blind") == codes(b, "blind") and codes(a, "feedback") == codes(b, "feedback")


def test_feedback_arm_learns_operator_weights_and_aggregates_deltas():
    res = run_lab(get_preset("cpp"), small(arms=("blind", "feedback")))
    w = res["trials"][0]["arms"]["feedback"]["operator_weights"]
    assert len(set(w.values())) > 3
    assert set(res["aggregate"]["feedback"]["delta_vs_blind"]) >= {"unique_error_patterns", "production_coverage_pct"}
    stat = res["aggregate"]["blind"]["metrics"]["unique_error_patterns"]
    assert stat["n"] == 2 and stat["stdev"] is not None


def test_adaptive_selector_rewards_novelty_and_keeps_exploring():
    sel = AdaptiveSelector(["a", "b", "c"])
    for _ in range(6):
        sel.reward("a", 3.0)
        sel.reward("b", 0.0)
    assert sel.weights["a"] > sel.weights["b"] and sel.weights["b"] >= 0.25
    p = sel.probabilities()
    assert abs(sum(p.values()) - 1) < 1e-9 and min(p.values()) >= sel.EXPLORE / 3 - 1e-9


def test_bug_signals_surface_in_experiment_for_hazardous_grammars():
    res = run_lab(get_preset("hazard"), small(trials=1, arms=("blind",)))
    assert res["trials"][0]["arms"]["blind"]["summary"]["bug_signals"] > 0


def test_ast_shapes_and_production_coverage_of_rejected_programs():
    t = GrammarTarget(CALC)
    tracker = ArmTracker(t)
    rec = run_test({"id": "a", "category": "x", "source": "x", "code": "1 + 2 * 3", "expected_status": "PASS"}, target=t)
    n1 = tracker.observe(rec, set())
    assert n1["new_ast_shape"] and n1["new_productions"] > 0
    rec2 = run_test({"id": "b", "category": "x", "source": "x", "code": "1 + * 3", "expected_status": "FAIL"}, target=t)
    n2 = tracker.observe(rec2, set())
    assert n2["new_pattern"] and not n2["new_ast_shape"]
    again = tracker.observe(rec2, set())
    assert not again["new_pattern"] and again["new_productions"] == 0
    info = t.analyze("1 + 2 * 3")
    assert ast_shape(info["earley"].tree).startswith("(expr")


def test_aggregate_handles_missing_arms():
    out = aggregate([{"arms": {"blind": {"status": "NOT_RUN", "summary": None}}}], ("blind",))
    assert out["blind"]["metrics"] is None and out["blind"]["trials_complete"] == 0
