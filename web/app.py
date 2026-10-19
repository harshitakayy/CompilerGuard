"""CompilerGuard web dashboard (Flask).  Run:  python main.py web"""
import os
import random
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, jsonify, request, send_from_directory, Response

from compiler import compile_source, FAULTS
from generator import ProgramGenerator
from fuzzer.engine import run_campaign, evaluate, minimize_bug, BUG_VERDICTS
from fuzzer import report
from ai import run_ai_guided, ai_status

HERE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=os.path.join(HERE, "static"), static_url_path="/static")
LAST = {"campaign": None, "ai": None}
LOCK = threading.Lock()


def _faults(data):
    return tuple(f for f in (data.get("faults") or []) if f in FAULTS)


def _int(data, key, default, lo, hi):
    try:
        return max(lo, min(hi, int(data.get(key, default))))
    except (TypeError, ValueError):
        return default


@app.get("/")
def index():
    return send_from_directory(HERE, "index.html")


@app.get("/api/status")
def status():
    return jsonify({"ai": ai_status(), "faults": FAULTS})


@app.post("/api/compile")
def api_compile():
    d = request.get_json(force=True, silent=True) or {}
    src, faults = str(d.get("source", ""))[:20000], _faults(d)
    res = compile_source(src, faults, detail=True)
    ev = evaluate(src, faults, expect_valid=False)
    res.pop("coverage", None)
    res["oracle"] = {"output": ev["ref_output"], "error": ev["ref_error"], "verdict": ev["verdict"]}
    return jsonify(res)


@app.post("/api/generate")
def api_generate():
    d = request.get_json(force=True, silent=True) or {}
    seed = d.get("seed")
    return jsonify({"source": ProgramGenerator(seed if isinstance(seed, int) else random.randint(0, 10**6)).generate()})


@app.post("/api/fuzz")
def api_fuzz():
    d = request.get_json(force=True, silent=True) or {}
    c = run_campaign(_int(d, "n_valid", 30, 5, 200), _int(d, "n_mutants", 150, 10, 2000),
                     _int(d, "seed", 1, 0, 10**9), _faults(d), bool(d.get("feedback", True)))
    with LOCK:
        LAST["campaign"], LAST["ai"] = c, None
    recs = [{"id": r["id"], "kind": r["kind"], "mutation": r["mutation"], "label": r["label"],
             "status": r["status"], "signature": r["signature"], "verdict": r["verdict"],
             "detail": r.get("detail"), "source": r["source"][:600]} for r in c["records"]]
    report.save(c)
    return jsonify({"summary": c["summary"], "records": recs})


@app.post("/api/ai")
def api_ai():
    d = request.get_json(force=True, silent=True) or {}
    out = run_ai_guided(_faults(d), _int(d, "seed", 1, 0, 10**9), _int(d, "rounds", 2, 1, 4),
                        _int(d, "n_tests", 10, 3, 20), d.get("provider") or None, d.get("api_key") or None)
    with LOCK:
        LAST["ai"] = out
    return jsonify(out)


@app.post("/api/minimize")
def api_minimize():
    d = request.get_json(force=True, silent=True) or {}
    src, faults = str(d.get("source", ""))[:20000], _faults(d)
    ev = evaluate(src, faults, expect_valid=bool(d.get("expect_valid")), must_fail=bool(d.get("must_fail")))
    if ev["verdict"] not in BUG_VERDICTS:
        return jsonify({"minimized": None, "verdict": ev["verdict"],
                        "message": "This program does not trigger a bug, so there is nothing to minimise."})
    rec = dict(ev, source=src, expect_valid=bool(d.get("expect_valid")), must_fail=bool(d.get("must_fail")))
    return jsonify({"minimized": minimize_bug(rec, faults), "verdict": ev["verdict"], "message": ev.get("detail")})


def _current_report():
    with LOCK:
        c, ai = LAST["campaign"], LAST["ai"]
    if c is None:
        c = run_campaign(30, 150, 1, ())
    return c, ai


@app.get("/api/report/latest.md")
def report_md():
    c, ai = _current_report()
    return Response(report.to_markdown(c, ai), mimetype="text/markdown",
                    headers={"Content-Disposition": "attachment; filename=compilerguard_report.md"})


@app.get("/api/report/latest.json")
def report_json():
    import json
    c, ai = _current_report()
    slim = {"summary": c["summary"], "ai": ai,
            "records": [{k: v for k, v in r.items() if k != "coverage"} for r in c["records"]]}
    return Response(json.dumps(slim, indent=1), mimetype="application/json",
                    headers={"Content-Disposition": "attachment; filename=compilerguard_report.json"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), threaded=True)
