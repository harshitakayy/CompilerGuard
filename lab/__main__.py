"""Command-line lab: ``python -m lab --target cpp --trials 3``.

Runs the three-approach, equal-budget experiment on a built-in target or on your
own grammar file (``--grammar my.gr``) and prints the comparison table.
"""

import argparse
import sys

from ai.ai_generator import AIGenerator
from grammarkit.grammar import GrammarError
from harness.reporting import build_metadata, create_run_dir, utc_now, write_json

from .experiment import ARM_LABELS, METRICS, LabConfig, run_lab
from .targets import PRESETS, GrammarTarget, get_preset


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    p = argparse.ArgumentParser(prog="python -m lab", description="Equal-budget mutation vs feedback vs AI experiment.")
    p.add_argument("--target", default="cpp", choices=list(PRESETS))
    p.add_argument("--grammar", help="path to your own grammar file (overrides --target)")
    p.add_argument("--budget", type=int, default=60)
    p.add_argument("--seed-tests", type=int, default=20)
    p.add_argument("--batch", type=int, default=10)
    p.add_argument("--trials", type=int, default=3)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--ai", action="store_true", help="include the AI-guided arm (needs OPENAI_API_KEY)")
    args = p.parse_args(argv)

    try:
        target = GrammarTarget(open(args.grammar, encoding="utf-8").read(), name=args.grammar) if args.grammar else get_preset(args.target)
    except GrammarError as e:
        print(f"Grammar error{f' on line {e.line}' if e.line else ''}: {e.message}")
        return 2
    cfg = LabConfig(budget=args.budget, seed_tests=args.seed_tests, batch=args.batch, trials=args.trials, seed=args.seed)
    ai = AIGenerator(grammar=target.grammar_text, notes=target.notes or None, language=target.name) if args.ai else None
    began = utc_now()
    print(f"CompilerGuard lab · target: {target.name} · {len(target.grammar.alts)} productions · budget {cfg.budget}/arm · {cfg.trials} trial(s)")
    res = run_lab(target, cfg, ai, progress=lambda m, pct=None: print("  " + m))
    keys = [k for k in ARM_LABELS if res["aggregate"][k]["metrics"]]
    print()
    print(f"{'Metric':<34}" + "".join(f"{ARM_LABELS[k]:<32}" for k in keys))
    for mid, label, d in [(m, m.replace('_', ' '), 1) for m in METRICS]:
        row = f"{label:<34}"
        for k in keys:
            s = res["aggregate"][k]["metrics"][mid]
            row += f"{s['mean']:.2f}" + (f" ± {s['stdev']:.2f}" if s["stdev"] is not None else "") + " " * 14
        print(row)
    for k in ARM_LABELS:
        if not res["aggregate"][k]["metrics"]:
            print(f"\n{ARM_LABELS[k]}: NOT RUN — {res['trials'][0]['arms'][k]['reason']}")
    run_dir = create_run_dir(None, label=f"lab-{target.id}", seed=cfg.seed)
    write_json(run_dir / "lab_result.json", res)
    write_json(run_dir / "experiment_metadata.json", build_metadata("lab", run_dir.name, res["config"], {"ai_requested": args.ai}, began, utc_now()))
    print(f"\nReports written to: {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
