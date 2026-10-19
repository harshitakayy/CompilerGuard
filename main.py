"""CompilerGuard command-line entry point.

  python main.py web                     start the web dashboard (http://localhost:5000)
  python main.py fuzz  [--fault NAME]    run a fuzzing campaign in the terminal
  python main.py ai    [--fault NAME]    run the AI-guided pipeline in the terminal
  python main.py compile FILE            compile and run one CG-Lang file
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser(description="CompilerGuard")
    ap.add_argument("command", choices=["web", "fuzz", "ai", "compile"])
    ap.add_argument("file", nargs="?")
    ap.add_argument("--fault", action="append", default=[], help="plant a bug (see compiler.FAULTS)")
    ap.add_argument("--valid", type=int, default=30)
    ap.add_argument("--mutants", type=int, default=150)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--rounds", type=int, default=2)
    a = ap.parse_args()

    if a.command == "web":
        from web.app import app
        app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False, threaded=True)
    elif a.command == "compile":
        from compiler import compile_source
        r = compile_source(open(a.file, encoding="utf-8").read(), a.fault)
        print(json.dumps({k: r[k] for k in ("status", "error_type", "message", "line", "col", "output", "warnings")}, indent=2))
    elif a.command == "fuzz":
        from tests.test_runner import print_campaign
        print_campaign(a.valid, a.mutants, a.seed, a.fault)
    else:
        from tests.test_runner import print_ai
        print_ai(a.seed, a.rounds, a.fault)


if __name__ == "__main__":
    main()
