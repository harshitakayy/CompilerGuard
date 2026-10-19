"""Fuzzing engine: grammar-based + mutation-based + coverage-guided feedback + differential oracle."""
import random
import time
from compiler import compile_source
from generator import generate_programs, mutate
from . import reference
from .minimizer import minimize

BUG_VERDICTS = ("BUG_CRASH", "BUG_FALSE_ACCEPT", "BUG_WRONG_OUTPUT", "BUG_FALSE_REJECT")

STRESS_CASES = [
    ("empty program", ""),
    ("only a comment", "# nothing here\n"),
    ("only whitespace", "   \n\t\n"),
    ("deep parentheses (500)", "x = " + "(" * 500 + "1" + ")" * 500 + ";"),
    ("deep parentheses (99)", "x = " + "(" * 99 + "1" + ")" * 99 + ";\nprint x;"),
    ("deep unary minus (400)", "x = " + "-" * 400 + "1;"),
    ("deep nested blocks (120)", "x = 1;\n" + "if (x < 2) {\n" * 120 + "print x;\n" + "}\n" * 120),
    ("long expression chain (5000)", "x = 1" + " + 1" * 5000 + ";\nprint x;"),
    ("huge integer literal", "x = " + "9" * 5000 + ";"),
    ("18-digit literal", "x = 999999999999999999;\nprint x;"),
    ("numeric explosion loop", "x = 9;\nwhile (1 < 2) { x = x * x; }"),
    ("infinite loop", "x = 0;\nwhile (x < 1) { y = 1; }"),
    ("unicode input", "x = \u00e9;"),
    ("null byte", "x = 1;\x00"),
    ("lone brace", "}"),
    ("windows line endings", "x = 1;\r\nprint x;\r\n"),
    ("float formatting", "x = 0.1 + 0.2;\nprint x;\nprint 10 / 4;\nprint 7 % 3;\nprint -7 % 3;"),
    ("left associativity", "print 10 - 3 - 2;\nprint 100 / 10 / 5;\nprint 2 * 3 % 4;"),
    ("unary vs binary minus", "print 5 - -3;\nprint -(2 + 3) * 2;"),
    ("division by runtime zero", "y = 0;\nprint 1 / y;"),
    ("modulo by runtime zero", "y = 0;\nprint 5 % y;"),
]


def evaluate(source, faults=(), expect_valid=False, must_fail=False):
    """Run the compiler AND the oracle on one program and classify the outcome."""
    c = compile_source(source, faults)
    v = {"status": c["status"], "error_type": c["error_type"], "message": c["message"],
         "line": c["line"], "col": c["col"], "signature": c["signature"], "output": c["output"],
         "coverage": c["coverage"], "ref_output": None, "ref_error": None, "verdict": "OK"}
    if c["status"] == "CRASH":
        v["verdict"] = "BUG_CRASH"
        v["detail"] = "%s: %s" % (c["crash"], (c["message"] or "")[:120])
        return v
    runtime_fail = c["status"] == "FAIL" and c["error_type"] in ("RUNTIME_ERROR", "LIMIT_ERROR", "INPUT_ERROR")
    if runtime_fail or (c["status"] == "FAIL" and not expect_valid):
        v["verdict"] = "OK_REJECTED"
        return v
    ref = reference.run(source)                    # only reached when it is safe to execute
    v["ref_output"], v["ref_error"] = ref["output"], ref["error"]
    if c["status"] == "PASS":
        if ref["ok"]:
            if ref["output"] != c["output"]:
                v["verdict"] = "BUG_WRONG_OUTPUT"
                v["detail"] = "compiler printed %s but reference printed %s" % (
                    c["output"][:6], ref["output"][:6])
        elif must_fail:
            v["verdict"] = "BUG_FALSE_ACCEPT"
            v["detail"] = "invalid program was accepted"
        else:
            v["verdict"] = "SUSPECT_ACCEPT"
            v["detail"] = "compiler accepted, reference said: %s" % ref["error"]
    else:                                           # FAIL on a program expected to be valid
        if ref["ok"]:
            v["verdict"] = "BUG_FALSE_REJECT"
            v["detail"] = "valid program rejected: %s" % c["signature"]
        else:
            v["verdict"] = "OK_REJECTED"
    return v


def _record(idx, kind, source, mutation, expect_valid, must_fail, faults, label=None):
    v = evaluate(source, faults, expect_valid, must_fail)
    v.update(id=idx, kind=kind, mutation=mutation, source=source, label=label,
             expect_valid=expect_valid, must_fail=must_fail)
    return v


def minimize_bug(rec, faults=()):
    target, sig = rec["verdict"], rec["signature"]
    ev, mf = rec.get("expect_valid", False), rec["verdict"] == "BUG_FALSE_ACCEPT" or rec.get("must_fail", False)

    def pred(s):
        r = evaluate(s, faults, ev, mf)
        return r["verdict"] == target and (target != "BUG_CRASH" or r["signature"] == sig)

    return minimize(rec["source"], pred)


def run_campaign(n_valid=30, n_mutants=150, seed=1, faults=(), feedback=True, n_minimize=8,
                 progress=None):
    t0 = time.time()
    rng = random.Random(seed)
    faults = tuple(faults or ())
    records, seen = [], set()
    growth = []

    def add(kind, source, mutation=None, expect_valid=False, must_fail=False, label=None):
        rec = _record(len(records), kind, source, mutation, expect_valid, must_fail, faults, label)
        seen.update(rec["coverage"])
        growth.append(len(seen))
        records.append(rec)
        return rec

    valid = generate_programs(n_valid, seed=seed)
    for p in valid:
        add("valid", p, expect_valid=True)

    corpus = list(valid)
    novel = []
    for _ in range(n_mutants):
        base = rng.choice(valid)
        m = mutate(base, rng, count=1)
        if not m:
            continue
        before = len(seen)
        rec = add("mutant", m["source"], m["mutation"], False, m["must_fail"])
        if len(seen) > before:
            novel.append(rec["source"])

    for label, src in STRESS_CASES:
        add("stress", src, label=label)

    if feedback:
        corpus = novel or corpus                    # coverage-guided: keep inputs that found new behaviour
        for _ in range(max(10, n_mutants // 2)):
            base = rng.choice(corpus)
            m = mutate(base, rng, count=rng.randint(2, 3))
            if not m:
                continue
            before = len(seen)
            rec = add("feedback", m["source"], m["mutation"])
            if len(seen) > before:
                corpus.append(rec["source"])

    summary = summarize(records, growth, faults, seed, time.time() - t0)
    bugs = {}
    for r in records:
        if r["verdict"] in BUG_VERDICTS:
            bugs.setdefault((r["verdict"], r["signature"], r.get("mutation") if r["verdict"] == "BUG_FALSE_ACCEPT" else None), r)
    summary["bugs"] = []
    for (verdict, sig, _), r in list(bugs.items()):
        item = {"id": r["id"], "verdict": verdict, "signature": sig, "kind": r["kind"],
                "mutation": r["mutation"], "label": r["label"], "detail": r.get("detail"),
                "source": r["source"][:1500], "minimized": None,
                "count": sum(1 for x in records if x["verdict"] == verdict and x["signature"] == sig)}
        if len(summary["bugs"]) < n_minimize and len(r["source"]) < 4000:
            item["minimized"] = minimize_bug(r, faults)
        summary["bugs"].append(item)
    return {"summary": summary, "records": records}


def summarize(records, growth, faults, seed, seconds):
    verdicts, kinds, sigs = {}, {}, {}
    for r in records:
        verdicts[r["verdict"]] = verdicts.get(r["verdict"], 0) + 1
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
        s = sigs.setdefault(r["signature"], {"signature": r["signature"], "count": 0, "example": r["source"][:200]})
        s["count"] += 1
    status = {"PASS": 0, "FAIL": 0, "CRASH": 0}
    for r in records:
        status[r["status"]] += 1
    cov = set()
    rules = set()
    for r in records:
        cov.update(r["coverage"])
    rules = {c for c in cov if not c.startswith("sig:")}
    total_bugs = sum(verdicts.get(v, 0) for v in BUG_VERDICTS)
    return {
        "total": len(records), "verdicts": verdicts, "kinds": kinds, "status": status,
        "signatures": sorted(sigs.values(), key=lambda s: -s["count"]),
        "unique_signatures": len(sigs), "rules_covered": len(rules),
        "coverage_growth": growth, "bug_count": total_bugs, "faults": list(faults),
        "seed": seed, "seconds": round(seconds, 2),
        "suspects": verdicts.get("SUSPECT_ACCEPT", 0),
    }
