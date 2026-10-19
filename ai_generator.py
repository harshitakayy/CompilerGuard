"""AI-guided targeted test generation.

Loop:  compiler errors -> error patterns -> prompt to an LLM -> targeted tests -> compiler -> new
patterns -> next round.  Works with Anthropic, OpenAI or Gemini (API key in environment
variables).  If no key is set / the call fails, an offline heuristic generator is used so the
pipeline (and the demo) never breaks; the result says clearly which source produced the tests.
"""
import json
import os
import random
import urllib.request
import urllib.error

from compiler import compile_source
from generator import generate_programs, mutate
from fuzzer.engine import evaluate, BUG_VERDICTS

GRAMMAR = """CG-Lang grammar:
program := statement*
statement := 'print' expr ';' | IDENT '=' expr ';' | 'if' '(' expr RELOP expr ')' block ['else' block]
           | 'while' '(' expr RELOP expr ')' block
block := '{' statement* '}'      RELOP := == != < <= > >=
expr := term (('+'|'-') term)* ; term := unary (('*'|'/'|'%') unary)* ; unary := '-' unary | primary
primary := NUMBER | IDENT | '(' expr ')'     NUMBER := integer or decimal (max 18 digits)
Comments start with '#'. Semantic rules: variables must be assigned before use; literal division by zero is an error."""


def _provider(preferred=None, api_key=None):
    if preferred in ("anthropic", "openai", "gemini") and api_key:
        return preferred, api_key
    env = {"anthropic": os.getenv("ANTHROPIC_API_KEY"), "openai": os.getenv("OPENAI_API_KEY"),
           "gemini": os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")}
    if preferred in env and env[preferred]:
        return preferred, env[preferred]
    forced = os.getenv("AI_PROVIDER")
    if forced in env and env[forced]:
        return forced, env[forced]
    for name in ("anthropic", "openai", "gemini"):
        if env[name]:
            return name, env[name]
    return None, None


def ai_status():
    name, _ = _provider()
    return {"provider": name, "available": name is not None,
            "mode": ("LLM (%s)" % name) if name else "offline heuristic fallback (no API key found)"}


def _post(url, headers, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode())


def _call_llm(provider, key, prompt):
    if provider == "anthropic":
        d = _post("https://api.anthropic.com/v1/messages",
                  {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                  {"model": os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"), "max_tokens": 3000,
                   "messages": [{"role": "user", "content": prompt}]})
        return "".join(b.get("text", "") for b in d["content"])
    if provider == "openai":
        d = _post("https://api.openai.com/v1/chat/completions",
                  {"Authorization": "Bearer " + key, "content-type": "application/json"},
                  {"model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                   "messages": [{"role": "user", "content": prompt}]})
        return d["choices"][0]["message"]["content"]
    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    d = _post("https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent?key=%s" % (model, key),
              {"content-type": "application/json"},
              {"contents": [{"parts": [{"text": prompt}]}]})
    return d["candidates"][0]["content"]["parts"][0]["text"]


def build_prompt(patterns, covered, n):
    lines = ["You are a compiler test engineer. Below is a tiny language and the error patterns "
             "its compiler produced during fuzzing.", GRAMMAR, "", "Observed compiler outcomes (signature, count, example):"]
    for p in patterns[:12]:
        lines.append("- %s | seen %d times | example: %s" % (p["signature"], p["count"], p["example"][:90].replace("\n", " ")))
    lines += ["", "Already covered outcome signatures: " + "; ".join(sorted(covered)[:30]), "",
              "Write %d NEW CG-Lang test programs that target edge cases NEAR these error patterns or "
              "outcomes NOT yet covered (boundary numbers, nesting, operator-precedence corner cases, "
              "unusual spacing/comments, semantic errors, scoping inside if/else and while, etc.). "
              "Mix invalid and valid programs. Each program must be short (max 8 lines)." % n,
              "Respond with ONLY a JSON array of %d strings. No explanation, no markdown fences." % n]
    return "\n".join(lines)


def _parse_json_list(text):
    a, b = text.find("["), text.rfind("]")
    if a < 0 or b < 0:
        raise ValueError("no JSON array in response")
    items = json.loads(text[a:b + 1])
    return [s for s in items if isinstance(s, str) and 0 < len(s) < 3000]


EDGE_BANK = [
    "x = 1;\nprint x +;", "x = (((1 + 2) * 3);", "x = 1 +* 2;", "x = ;", "print ;", "if (1 < 2) { }",
    "if 1 < 2 { print 1; }", "while (1 < 2 { print 1; }", "x = 5 / (3 - 3);", "x = 1.;", "x = .5;",
    "x = 1.2.3;", "x = 12abc;", "print 1 // 2;", "y = x;", "x = 1;\nif (x == 1) {\n y = 2;\n}\nprint y;",
    "if (1 < 2) {\n z = 1;\n} else {\n z = 2;\n}\nprint z;", "x = 0.1 + 0.2;\nprint x;",
    "x = 10 % 0;", "x = - - - 5;\nprint x;", "else { print 1; }", "x = 1; } ", "x = 1 # comment\n;\nprint x;",
    "x=1;y=2;print x+y*3;", "print 1 < 2;", "x = 5 5;", "x = (1)(2);", "if (1 < 2 < 3) { print 1; }",
    "x = 1;\nwhile (x < 3) { x = x + 1; }\nprint x;", "print " + "-" * 50 + "1;",
]


def _targeted_variants(source, signature, rng, n):
    """Offline 'AI': derive targeted tests from an observed error pattern."""
    et = signature.split(":")[0]
    if et == "SYNTAX_ERROR":
        ops = ["drop_semicolon", "drop_rparen", "drop_lparen", "drop_brace", "stray_operator",
               "double_operator", "missing_operand", "drop_relop", "keyword_typo", "drop_else"]
    elif et == "SEMANTIC_ERROR":
        ops = ["undefined_var", "div_by_zero", "swap_adjacent", "replace_number"]
    elif et == "LEXICAL_ERROR":
        ops = ["illegal_char", "number_glued_to_ident", "replace_number"]
    else:
        ops = None
    out = []
    for _ in range(n):
        m = mutate(source, rng, count=rng.randint(1, 2), ops=ops)
        if m:
            out.append(m["source"])
    return out


def generate_tests(patterns, covered, n, seed, provider=None, api_key=None, exclude=()):
    """Return (tests, info). Falls back to heuristics when the LLM is unavailable."""
    prov, key = _provider(provider, api_key)
    info = {"provider": prov, "used_fallback": False, "error": None}
    if prov:
        try:
            tests = _parse_json_list(_call_llm(prov, key, build_prompt(patterns, covered, n)))
            tests = [t for t in tests if t not in exclude]
            if tests:
                return tests[:n], info
            raise ValueError("empty response")
        except (urllib.error.URLError, urllib.error.HTTPError, ValueError, KeyError, TimeoutError, OSError) as e:
            info["error"] = "%s: %s" % (type(e).__name__, str(e)[:160])
    info["used_fallback"], info["provider"] = True, "offline-heuristic"
    rng = random.Random(seed)
    tests = []
    for p in patterns[:8]:
        base = generate_programs(1, seed=rng.randint(0, 10 ** 6), max_depth=1, max_stmts=3)[0]   # short, readable bases
        tests += _targeted_variants(base, p["signature"], rng, 2)
    bank = EDGE_BANK[:]
    rng.shuffle(bank)
    tests += bank
    seen, out = set(exclude), []
    for t in tests:
        if t not in seen:
            seen.add(t); out.append(t)
    return out[:n], info


def run_ai_guided(faults=(), seed=1, rounds=2, n_tests=10, provider=None, api_key=None):
    faults = tuple(faults or ())
    base = generate_programs(15, seed=seed)
    rng = random.Random(seed)
    covered, patterns = set(), {}

    def absorb(source, res):
        covered.add(res["signature"])
        p = patterns.setdefault(res["signature"], {"signature": res["signature"], "count": 0, "example": source})
        p["count"] += 1

    for p in base:
        absorb(p, evaluate(p, faults, expect_valid=True))
    for _ in range(40):
        m = mutate(rng.choice(base), rng)
        if m:
            absorb(m["source"], evaluate(m["source"], faults, False, m["must_fail"]))
    out = {"rounds": [], "baseline_signatures": len(covered), "faults": list(faults)}
    used = set()
    all_bugs = 0
    for r in range(1, rounds + 1):
        plist = sorted(patterns.values(), key=lambda p: -p["count"])
        tests, info = generate_tests(plist, covered, n_tests, seed + r, provider, api_key, used)
        used.update(tests)
        results, new_sigs = [], []
        for t in tests:
            ev = evaluate(t, faults)
            is_new = ev["signature"] not in covered
            if is_new:
                new_sigs.append(ev["signature"])
            absorb(t, ev)
            if ev["verdict"] in BUG_VERDICTS:
                all_bugs += 1
            results.append({"source": t, "status": ev["status"], "signature": ev["signature"],
                            "verdict": ev["verdict"], "new": is_new, "detail": ev.get("detail"),
                            "line": ev["line"], "col": ev["col"]})
        out["rounds"].append({
            "round": r, "provider": info["provider"], "used_fallback": info["used_fallback"],
            "error": info["error"], "patterns_sent": [{"signature": p["signature"], "count": p["count"]} for p in plist[:8]],
            "tests": results, "new_signatures": new_sigs})
    out["total_tests"] = sum(len(r["tests"]) for r in out["rounds"])
    out["new_signatures_total"] = sum(len(r["new_signatures"]) for r in out["rounds"])
    out["bugs_found"] = all_bugs
    out["final_signatures"] = len(covered)
    return out
