"""Writes campaign / AI-guided results to reports/ as JSON and Markdown."""
import json
import os
import time

REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")


def _md_table(rows, headers):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c).replace("|", "\\|").replace("\n", " ") for c in r) + " |")
    return "\n".join(out)


def to_markdown(campaign, ai=None):
    s = campaign["summary"]
    L = ["# CompilerGuard test report", "",
         "- Generated: %s" % time.strftime("%Y-%m-%d %H:%M:%S"),
         "- Seed: %s, duration: %ss" % (s["seed"], s["seconds"]),
         "- Planted faults: %s" % (", ".join(s["faults"]) or "none (clean compiler)"), "",
         "## Summary", "",
         "| Metric | Value |", "|---|---|",
         "| Total test programs | %d |" % s["total"],
         "| Accepted (PASS) / Rejected (FAIL) / Crashed | %d / %d / %d |" % (s["status"]["PASS"], s["status"]["FAIL"], s["status"]["CRASH"]),
         "| Bugs detected | %d |" % s["bug_count"],
         "| Unique compiler outcomes (error patterns) | %d |" % s["unique_signatures"],
         "| Grammar/semantic rules covered | %d |" % s["rules_covered"], "",
         "## Verdicts", "", _md_table(sorted(s["verdicts"].items()), ["Verdict", "Count"]), "",
         "## Tests by source", "", _md_table(sorted(s["kinds"].items()), ["Kind", "Count"]), ""]
    if s["bugs"]:
        L += ["## Bugs found (with minimised reproducers)", "",
              _md_table([(b["verdict"], b["signature"], b["count"], "`%s`" % (b["minimized"] or b["source"][:80]).replace("\n", " ")[:160])
                         for b in s["bugs"]], ["Verdict", "Outcome", "Hits", "Minimal reproducer"]), ""]
    else:
        L += ["## Bugs found", "", "None. Every valid program was accepted with output identical to the reference "
              "implementation, and every guaranteed-invalid mutant was rejected.", ""]
    L += ["## Compiler outcomes observed", "",
          _md_table([(x["signature"], x["count"]) for x in s["signatures"]], ["Outcome", "Count"]), ""]
    if ai:
        L += ["## AI-guided testing", "",
              "- Baseline outcomes before AI: %d, after AI: %d (+%d new)" % (ai["baseline_signatures"], ai["final_signatures"], ai["new_signatures_total"]),
              "- AI-generated tests run: %d, bugs found by them: %d" % (ai["total_tests"], ai["bugs_found"]), ""]
        for r in ai["rounds"]:
            L += ["### Round %d (source: %s)" % (r["round"], r["provider"]), "",
                  "New outcomes: %s" % (", ".join(r["new_signatures"]) or "none"), ""]
    return "\n".join(L)


def save(campaign, ai=None):
    os.makedirs(REPORT_DIR, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    slim = {"summary": campaign["summary"],
            "records": [{k: v for k, v in r.items() if k != "coverage"} for r in campaign["records"]],
            "ai": ai}
    paths = {}
    for name, content in (("json", json.dumps(slim, indent=1)), ("md", to_markdown(campaign, ai))):
        for fn in ("report_%s.%s" % (stamp, name), "latest.%s" % name):
            with open(os.path.join(REPORT_DIR, fn), "w", encoding="utf-8") as f:
                f.write(content)
        paths[name] = "reports/latest." + name
    return paths
