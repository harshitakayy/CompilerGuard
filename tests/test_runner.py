"""Terminal test runner: python tests/test_runner.py   (or: python main.py fuzz / ai)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fuzzer.engine import run_campaign
from fuzzer import report
from ai import run_ai_guided, ai_status


def print_campaign(n_valid=30, n_mutants=150, seed=1, faults=()):
    c = run_campaign(n_valid, n_mutants, seed, faults)
    s, recs = c["summary"], c["records"]
    valid = [r for r in recs if r["kind"] == "valid"]
    mutants = [r for r in recs if r["kind"] == "mutant"]
    print("\n========== VALID TESTING (grammar-generated) ==========")
    print("Total Tests : %d\nCorrect     : %d\nIncorrect   : %d" % (
        len(valid), sum(r["verdict"] == "OK" for r in valid), sum(r["verdict"] != "OK" for r in valid)))
    print("\n========== INVALID TESTING (mutation-generated) ==========")
    must = [r for r in mutants if r["must_fail"]]
    print("Guaranteed-invalid mutants : %d\nCorrectly rejected         : %d\nAccepted (BUG)             : %d" % (
        len(must), sum(r["status"] == "FAIL" for r in must), sum(r["verdict"] == "BUG_FALSE_ACCEPT" for r in must)))
    print("\n========== STRESS / FEEDBACK ==========")
    print("Stress cases: %d, crashes: %d | feedback-guided tests: %d" % (
        s["kinds"].get("stress", 0), sum(r["verdict"] == "BUG_CRASH" and r["kind"] == "stress" for r in recs),
        s["kinds"].get("feedback", 0)))
    print("Unique compiler outcomes: %d | rules covered: %d" % (s["unique_signatures"], s["rules_covered"]))
    print("\n========== RESULT ==========")
    print("Total programs: %d   Bugs found: %d   Planted faults: %s" % (s["total"], s["bug_count"], ", ".join(s["faults"]) or "none"))
    for b in s["bugs"]:
        print("  [%s] %s\n      minimal reproducer: %s" % (b["verdict"], b["signature"], (b["minimized"] or "")[:100]))
    paths = report.save(c)
    print("\nReport saved to", paths["md"], "and", paths["json"])
    return c


def print_ai(seed=1, rounds=2, faults=()):
    print("\n========== AI-GUIDED TESTING ==========")
    print("Mode:", ai_status()["mode"])
    ai = run_ai_guided(faults, seed, rounds, 10)
    for r in ai["rounds"]:
        print("Round %d (%s): %d tests, new outcomes: %d" % (r["round"], r["provider"], len(r["tests"]), len(r["new_signatures"])))
        for i, t in enumerate(r["tests"][:5], 1):
            print("   AI Test #%d -> %s%s" % (i, t["signature"], "  (NEW)" if t["new"] else ""))
    print("Outcomes before/after AI: %d -> %d | bugs found by AI tests: %d" % (
        ai["baseline_signatures"], ai["final_signatures"], ai["bugs_found"]))
    return ai


if __name__ == "__main__":
    f = [a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--fault=")]
    print_campaign(faults=f)
    print_ai(faults=f)
