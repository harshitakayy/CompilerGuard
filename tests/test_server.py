import http.client
import json
import re
import threading
import time
from pathlib import Path

import pytest

import server
from tests.fakes import ScriptedAI

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def api(tmp_path_factory):
    srv = server.make_server("127.0.0.1", 0)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    def call(method, path, body=None, raw=None):
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
        data = raw if raw is not None else (json.dumps(body) if body is not None else None)
        c.request(method, path, data, {"Content-Type": "application/json"})
        r = c.getresponse()
        text = r.read()
        try:
            return r.status, json.loads(text)
        except ValueError:
            return r.status, text.decode()

    yield call
    srv.shutdown()


def wait_job(api, job_id, timeout=90):
    for _ in range(int(timeout / 0.3)):
        status, job = api("GET", f"/api/jobs/{job_id}")
        if job["status"] != "running":
            return job
        time.sleep(0.3)
    raise AssertionError("job did not finish")


def test_health_and_presets(api):
    s, h = api("GET", "/api/health")
    assert s == 200 and h["ok"] and set(h["targets"]) == {"cglang", "cpp", "calc", "json", "hazard"} and "available" in h["ai"]
    s, p = api("GET", "/api/presets")
    assert [x["id"] for x in p["presets"]][:2] == ["cglang", "cpp"] and "translation_unit" in p["presets"][1]["grammar"]


def test_compile_returns_verdict_oracle_tokens_tree_and_rules(api):
    s, d = api("POST", "/api/compile", {"target": "cpp", "source": "int main() { int x = 1 + 2; return x; }"})
    assert s == 200 and d["response"] == {"status": "PASS"} and d["oracle"]["status"] == "PASS" and not d["signal"]
    assert d["tree"]["n"] == "translation_unit" and d["tokens"][0]["kind"] == "int"
    assert d["rules_used"]["function_def"] == 1 and any("function_def" in p["label"] for p in d["productions_used"])
    s, bad = api("POST", "/api/compile", {"target": "cpp", "source": "int main() { return 0 }"})
    assert bad["response"]["type"] == "SYNTAX_ERROR" and bad["tree"] is None and bad["expected"]


def test_compile_cglang_uses_the_original_compiler(api):
    s, d = api("POST", "/api/compile", {"target": "cglang", "source": "y = x + 1;"})
    assert d["response"]["type"] == "SEMANTIC_ERROR" and d["oracle"]["type"] == "SEMANTIC_ERROR"


def test_custom_grammar_flow(api):
    g = "list -> '[' (ID (',' ID)*)? ']'"
    s, a = api("POST", "/api/grammar/analyze", {"grammar": g})
    assert a["ok"] and a["grammar"]["stats"]["rules"] == 1 and a["samples"]
    s, d = api("POST", "/api/compile", {"grammar": g, "source": "[ a , b ]"})
    assert d["response"]["status"] == "PASS" and d["rules_used"] == {"list": 1}
    s, d = api("POST", "/api/compile", {"grammar": g, "source": "[ a , ]"})
    assert d["response"]["status"] == "FAIL" and d["expected"] == ["ID"]
    s, e = api("POST", "/api/grammar/analyze", {"grammar": "a -> b"})
    assert e["ok"] is False and e["error"]["line"] == 1
    s, e = api("POST", "/api/compile", {"grammar": "a -> b", "source": ""})
    assert s == 400 and "Undefined nonterminal" in e["error"] and e["line"] == 1


def test_hazard_grammar_raises_a_signal_through_the_api(api):
    s, d = api("POST", "/api/compile", {"target": "hazard", "source": "a b x"})
    assert d["signal"] and "STATUS_MISMATCH" in d["reasons"]


def test_generate_valid_and_mutants(api):
    s, v = api("POST", "/api/generate", {"target": "calc", "kind": "valid", "count": 6, "seed": 3})
    assert s == 200 and len(v["rows"]) == 6 and all(r["actual"] == "PASS" for r in v["rows"])
    s, m = api("POST", "/api/generate", {"target": "cpp", "kind": "mutants", "count": 25, "seed": 3})
    assert len(m["rows"]) == 25 and len({r["operator"] for r in m["rows"]}) > 8
    assert all({"code", "expected", "actual", "signal", "intent"} <= set(r) for r in m["rows"])
    s, big = api("POST", "/api/generate", {"target": "calc", "kind": "mutants", "count": 5000})
    assert len(big["rows"]) <= 80


def test_experiment_job_reports_all_metrics_and_saves_results(api):
    s, d = api("POST", "/api/experiment", {"target": "calc", "budget": 30, "seed_tests": 10, "trials": 1, "seed": 5})
    job = wait_job(api, d["job_id"])
    assert job["status"] == "done" and job["progress"] == 100
    r = job["result"]
    arms = r["trials"][0]["arms"]
    assert arms["blind"]["status"] == arms["feedback"]["status"] == "COMPLETE" and arms["ai"]["status"] == "NOT_RUN"
    assert r["ai_status"]["requested"] is False
    saved = ROOT / r["report_dir"]
    assert (saved / "lab_result.json").exists() and (saved / "experiment_metadata.json").exists()
    import shutil
    shutil.rmtree(saved, ignore_errors=True)


def test_browser_supplied_key_is_used_but_never_stored_or_echoed(api, monkeypatch):
    seen = {}

    def factory(**kw):
        seen.update(kw)
        return ScriptedAI(available=False, reason="scripted: test double")

    monkeypatch.setattr(server, "AIGenerator", factory)
    secret = "sk-test-SECRET-1234567890abcdef"
    s, d = api("POST", "/api/experiment", {"target": "calc", "budget": 30, "seed_tests": 10, "trials": 1,
                                           "ai": {"enabled": True, "api_key": secret}})
    job = wait_job(api, d["job_id"])
    assert seen["api_key"] == secret and seen["language"] == "Calculator" and "expr" in seen["grammar"]
    r = job["result"]
    assert secret not in json.dumps(job)
    assert secret not in (ROOT / r["report_dir"] / "lab_result.json").read_text()
    import shutil
    shutil.rmtree(ROOT / r["report_dir"], ignore_errors=True)


def test_input_validation_and_errors(api):
    assert api("POST", "/api/compile", {"target": "nope", "source": ""})[0] == 400
    assert api("POST", "/api/compile", raw="not json")[0] == 400
    assert api("POST", "/api/compile", {"target": "calc", "source": "x" * 30000})[0] == 400
    assert api("GET", "/api/nothing")[0] == 404 and api("GET", "/api/jobs/unknown")[0] == 404
    s, d = api("POST", "/api/experiment", {"target": "calc", "budget": 99999, "trials": 99, "seed_tests": 99999})
    assert s == 200  # clamped, not trusted
    job = wait_job(api, d["job_id"], 180)
    assert job["result"]["config"]["budget"] == 200 and job["result"]["config"]["trials"] == 5
    import shutil
    shutil.rmtree(ROOT / job["result"]["report_dir"], ignore_errors=True)


def test_static_files_and_path_traversal(api):
    s, html = api("GET", "/")
    assert s == 200 and "CompilerGuard" in html and 'src="app.js"' in html
    assert api("GET", "/style.css")[0] == 200 and api("GET", "/app.js")[0] == 200
    assert api("GET", "/../server.py")[0] == 404 and api("GET", "/%2e%2e/server.py")[0] == 404


def test_every_element_id_used_by_the_frontend_exists_in_the_page():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    ids = set(re.findall(r'id="([\w-]+)"', html))
    used = set(re.findall(r'\$\("([\w-]+)"\)', js))
    assert used - ids == set(), f"missing in index.html: {used - ids}"
    assert "https://" not in js.replace("https://fonts", "")  # no external calls from the app
