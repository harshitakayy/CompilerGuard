"""Iterative AI feedback loop shared by the pipeline and the evaluation.

Each round: summarise compiler feedback from everything executed so far, ask
the AI generator for new tests, drop duplicates, execute the rest and feed the
new compiler results into the next round. The loop stops when the budget is
met, the round limit is reached or the AI service reports a fatal error.
"""

from ai.ai_generator import NON_FATAL_ERROR_CODES

from .analysis import build_feedback
from .execution import run_tests
from .oracle import reference_check


def make_ai_test(code, round_no, index, model, patterns_sent, target=None):
    """AI programs carry no author-declared intent, so the expected outcome
    is the independent oracle's verdict."""
    verdict = target.oracle(code) if target is not None else reference_check(code)
    test = {
        "id": f"ai-r{round_no}-{index:02d}",
        "category": "ai_guided",
        "source": "ai",
        "code": code,
        "expected_status": verdict["status"],
        "expected_basis": "oracle",
        "provenance": {"round": round_no, "model": model, "patterns_sent": patterns_sent},
    }
    if verdict["status"] == "FAIL":
        test["expected_error_type"] = verdict["type"]
    return test


def run_ai_loop(ai, executed, budget, round_size, max_rounds, duplicates, patterns, echo=None, target=None, runner=None):
    """Run feedback rounds; returns a dict with ``status``, ``reason``,
    ``results`` (executed AI tests) and per-round ``rounds`` information."""
    say = echo or (lambda *_: None)
    available, reason = ai.availability()
    if not available:
        return {"status": "SKIPPED", "reason": reason, "results": [], "rounds": [], "budget_met": False}

    ai_results, rounds = [], []
    prev_patterns, had_error, last_reason = None, False, None

    for round_no in range(1, max_rounds + 1):
        remaining = budget - len(ai_results)
        if remaining <= 0:
            break
        request = min(round_size, remaining)
        so_far = executed + ai_results
        known_before = {r["error_pattern"] for r in so_far if r["error_pattern"]}
        feedback = build_feedback(so_far, previous_patterns=prev_patterns)
        result = ai.generate(feedback, request, [r["code"] for r in so_far])
        prev_patterns = known_before

        info = {
            "round": round_no,
            "requested": request,
            "status": result.status,
            "error_code": result.error_code,
            "reason": result.reason,
            "model": result.model,
            "usage": result.usage,
            "raw_count": result.raw_count,
            "rejected_in_validation": len(result.rejected),
            "patterns_sent": len(feedback["patterns"]),
            "duplicates_discarded": 0,
            "executed": 0,
            "new_patterns": [],
        }
        rounds.append(info)

        if result.status == "SKIPPED":
            return {"status": "SKIPPED", "reason": result.reason, "results": ai_results,
                    "rounds": rounds, "budget_met": False}
        if result.status == "ERROR":
            had_error, last_reason = True, result.reason
            say(f"  round {round_no}: AI error {result.error_code}: {result.reason}")
            if result.error_code not in NON_FATAL_ERROR_CODES:
                break
            continue

        tests = []
        for code in result.tests:
            if code in duplicates:
                info["duplicates_discarded"] += 1
                continue
            tests.append(
                make_ai_test(code, round_no, len(tests) + 1, result.model, len(feedback["patterns"]), target)
            )
        round_results = runner(tests) if runner else run_tests(tests, duplicates, patterns, target)
        ai_results.extend(round_results)
        info["executed"] = len(round_results)
        info["new_patterns"] = [r["error_pattern"] for r in round_results if r["new_pattern"]]
        say(
            f"  round {round_no}: requested {request}, executed {len(round_results)}, "
            f"new error patterns {len(info['new_patterns'])}"
        )

    if had_error:
        status = "PARTIAL" if ai_results else "FAILED"
    else:
        status = "COMPLETED"
    return {
        "status": status,
        "reason": last_reason,
        "results": ai_results,
        "rounds": rounds,
        "budget_met": len(ai_results) >= budget,
    }
