#!/usr/bin/env python
"""CompilerGuard backend: JSON API plus the web front end (standard library only).

    python server.py [--port 8000] [--host 127.0.0.1] [--open]

Endpoints (all JSON): GET /api/health, /api/presets, /api/jobs/<id>;
POST /api/grammar/analyze, /api/compile, /api/generate, /api/experiment.
An OpenAI key, if supplied by the browser, is used for that request only: it is
never stored, logged or written to reports.
"""

import argparse
import hashlib
import json
import mimetypes
import sys
import threading
import time
import traceback
import uuid
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from ai.ai_generator import AIGenerator  # noqa: E402
from grammarkit.grammar import Grammar, GrammarError  # noqa: E402
from grammarkit.mutate import SmartMutator  # noqa: E402
from harness.execution import run_test  # noqa: E402
from harness.oracle import compare_to_oracle  # noqa: E402
from harness.reporting import DEFAULT_REPORTS_DIR, build_metadata, create_run_dir, utc_now, write_json  # noqa: E402
from lab.experiment import LabConfig, run_lab  # noqa: E402
from lab.targets import PRESETS, GrammarTarget, get_preset, preset_info  # noqa: E402

VERSION = "2.0"
WEB = ROOT / "web"
MAX_BODY = 200_000
MAX_SOURCE = 20_000
_custom = OrderedDict()
JOBS, JOBS_LOCK = {}, threading.Lock()


class ApiError(Exception):
    def __init__(self, message, status=400, **extra):
        super().__init__(message)
        self.message, self.status, self.extra = message, status, extra


def resolve_target(payload):
    gtext = payload.get("grammar")
    if gtext is not None and payload.get("target") in (None, "custom"):
        key = hashlib.sha256(gtext.encode()).hexdigest()
        if key not in _custom:
            try:
                _custom[key] = GrammarTarget(gtext, "custom", "Custom grammar", "Your grammar")
            except GrammarError as e:
                raise ApiError("Grammar error: " + e.message, line=e.line)
            if len(_custom) > 24:
                _custom.popitem(last=False)
        return _custom[key]
    try:
        return get_preset(payload.get("target") or "cglang")
    except KeyError:
        raise ApiError("Unknown target")


def tree_json(node, tokens, budget):
    if node.alt is None:
        t = tokens[node.lo]
        return {"k": node.name, "t": t.text}
    kids = []

    def walk(n):
        for c in n.kids:
            if c.alt is not None and "~" in c.name:
                walk(c)
            elif c.alt is None or c.hi > c.lo:
                if budget[0] <= 0:
                    return
                budget[0] -= 1
                kids.append(tree_json(c, tokens, budget))

    walk(node)
    return {"n": node.name, "c": kids}


def api_compile(p):
    t, src = resolve_target(p), p.get("source", "")
    if not isinstance(src, str) or len(src) > MAX_SOURCE:
        raise ApiError("Source must be text under 20,000 characters")
    resp, orc = t.compile(src), t.oracle(src)
    reasons = compare_to_oracle(resp, orc)
    info = t.analyze(src)
    e, toks = info["earley"], info["tokens"]
    out = {"target": t.id, "response": resp, "oracle": orc, "signal": bool(reasons), "reasons": reasons,
           "tokens": [{"kind": k.kind, "text": k.text, "line": k.line, "col": k.col} for k in (toks or [])[:600]],
           "tree": None, "rules_used": {}, "productions_used": [], "expected": sorted(e.expected)[:20] if e and not e.ok else []}
    if e and e.ok and e.tree is not None:
        out["tree"] = tree_json(e.tree, toks, [1500])
        counts, stack = {}, [e.tree]
        while stack:
            n = stack.pop()
            if n.alt is not None:
                counts[n.alt] = counts.get(n.alt, 0) + 1
                stack += n.kids
        rules = {}
        for a, c in counts.items():
            alt = t.grammar.alts[a]
            if alt.lhs == alt.root:  # count uses of the user's own rules, not desugared helpers
                rules[alt.root] = rules.get(alt.root, 0) + c
        out["rules_used"] = rules
        out["productions_used"] = [{"label": t.grammar.label(a), "count": c} for a, c in sorted(counts.items(), key=lambda kv: -kv[1])[:60]]
    return out


def api_analyze(p):
    gtext = p.get("grammar", "")
    try:
        g = Grammar(gtext)
    except GrammarError as e:
        return {"ok": False, "error": e.to_dict()}
    out = {"ok": True, "grammar": g.to_dict(), "samples": []}
    try:
        t = resolve_target({"grammar": gtext})
        out["samples"] = [x["code"] for x in t.valid_programs(3, 7)]
    except ApiError:
        pass
    return out


def api_generate(p):
    t = resolve_target(p)
    count, seed = max(1, min(int(p.get("count", 20)), 80)), int(p.get("seed", 42))
    parents = t.valid_programs(max(12, count if p.get("kind") == "valid" else 12), seed)
    tests = parents[:count] if p.get("kind") == "valid" else SmartMutator(t, seed).generate(parents, count)
    rows = []
    for test in tests:
        r = run_test(test, target=t)
        rows.append({"id": r["id"], "code": r["code"], "category": r["category"], "operator": r.get("provenance", {}).get("operator"),
                     "intent": r.get("provenance", {}).get("intent"), "expected": r["expected_status"], "actual": r["actual_status"],
                     "response": r["compiler_response"], "signal": r["potential_compiler_bug"], "reasons": r["bug_reasons"], "pattern": r["error_pattern"]})
    return {"target": t.id, "rows": rows, "seed": seed}


def start_experiment(p):
    t = resolve_target(p)
    budget = max(20, min(int(p.get("budget", 60)), 200))
    cfg = LabConfig(budget=budget, seed_tests=max(5, min(int(p.get("seed_tests", 20)), budget - 5)),
                    batch=max(5, min(int(p.get("batch", 10)), 20)), trials=max(1, min(int(p.get("trials", 3)), 5)),
                    seed=int(p.get("seed", 42)), parents=30)
    aiopt = p.get("ai") or {}
    ai = None
    if aiopt.get("enabled"):
        ai = AIGenerator(grammar=t.grammar_text, notes=t.notes or None, language=t.name, api_key=(aiopt.get("api_key") or None))
    job_id = uuid.uuid4().hex[:10]
    job = {"id": job_id, "status": "running", "progress": 0, "log": [], "result": None, "error": None, "started": time.time()}
    with JOBS_LOCK:
        if sum(1 for j in JOBS.values() if j["status"] == "running") >= 2:
            raise ApiError("Two experiments are already running; please wait.", 429)
        JOBS[job_id] = job
        for old in [k for k, j in JOBS.items() if time.time() - j["started"] > 3600]:
            JOBS.pop(old, None)

    def progress(msg, pct=None):
        job["log"].append(msg)
        if pct is not None:
            job["progress"] = pct

    def work():
        began = utc_now()
        try:
            result = run_lab(t, cfg, ai, progress)
            result["ai_status"] = {"requested": bool(aiopt.get("enabled")), "available": bool(ai and ai.availability()[0]),
                                   "reason": None if not ai else ai.availability()[1], "model": getattr(ai, "model", None)}
            run_dir = create_run_dir(None, label=f"lab-{t.id}", seed=cfg.seed)
            write_json(run_dir / "lab_result.json", result)
            write_json(run_dir / "experiment_metadata.json", build_metadata("lab", run_dir.name, result["config"], result["ai_status"], began, utc_now()))
            result["report_dir"] = str(run_dir.relative_to(ROOT)) if run_dir.is_relative_to(ROOT) else str(run_dir)
            job["result"], job["progress"], job["status"] = result, 100, "done"
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            job["error"], job["status"] = f"{type(e).__name__}: {e}", "error"

    threading.Thread(target=work, daemon=True).start()
    return {"job_id": job_id}


def api_health():
    ok, reason = AIGenerator().availability()
    return {"ok": True, "version": VERSION, "ai": {"available": ok, "reason": reason, "model": AIGenerator().model},
            "targets": list(PRESETS), "reports_dir": str(DEFAULT_REPORTS_DIR.relative_to(ROOT))}


class Handler(BaseHTTPRequestHandler):
    server_version = "CompilerGuard/" + VERSION

    def log_message(self, fmt, *args):  # never log request bodies (they may hold a key)
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, status, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text") or ctype.endswith("json") else ""))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _api(self, method, path):
        try:
            if method == "GET":
                if path == "/api/health":
                    return self._send(200, api_health())
                if path == "/api/presets":
                    return self._send(200, {"presets": preset_info()})
                if path.startswith("/api/jobs/"):
                    job = JOBS.get(path.rsplit("/", 1)[1])
                    if not job:
                        raise ApiError("Unknown job", 404)
                    out = {k: job[k] for k in ("id", "status", "progress", "error")}
                    out["log"] = job["log"][-40:]
                    if job["status"] == "done":
                        out["result"] = job["result"]
                    return self._send(200, out)
                raise ApiError("Not found", 404)
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                raise ApiError("Request too large", 413)
            try:
                payload = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                raise ApiError("Body must be JSON")
            routes = {"/api/compile": api_compile, "/api/grammar/analyze": api_analyze, "/api/generate": api_generate, "/api/experiment": start_experiment}
            if path not in routes:
                raise ApiError("Not found", 404)
            return self._send(200, routes[path](payload))
        except ApiError as e:
            return self._send(e.status, {"error": e.message, **e.extra})
        except (ValueError, TypeError) as e:
            return self._send(400, {"error": f"Bad request: {e}"})
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            return self._send(500, {"error": f"Server error: {type(e).__name__}"})

    def do_GET(self):
        path = urlparse(self.path).path
        if path.startswith("/api/"):
            return self._api("GET", path)
        target = (WEB / ("index.html" if path in ("/", "") else path.lstrip("/"))).resolve()
        if WEB.resolve() not in target.parents and target != WEB.resolve() or not target.is_file():
            return self._send(404, b"Not found", "text/plain")
        self._send(200, target.read_bytes(), mimetypes.guess_type(str(target))[0] or "application/octet-stream")

    def do_POST(self):
        self._api("POST", urlparse(self.path).path)


def make_server(host="127.0.0.1", port=8000):
    sys.setrecursionlimit(20000)
    threading.stack_size(64 * 1024 * 1024)
    return ThreadingHTTPServer((host, port), Handler)


def main():
    ap = argparse.ArgumentParser(description="CompilerGuard web server")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--open", action="store_true", help="open the browser")
    args = ap.parse_args()
    srv = make_server(args.host, args.port)
    url = f"http://{args.host}:{args.port}/"
    print(f"CompilerGuard running at {url}  (Ctrl+C to stop)")
    if args.open:
        import webbrowser
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
