"""Equal-budget evaluation: mutation baseline vs AI-guided testing.

    python tests/evaluation.py [--budget 60] [--ai-seed-tests 20] [--trials 5]
                               [--seed 42] [--round-size 10] [--no-ai]

Design (per trial, one random seed):

* A pool of valid programs is generated from the grammar and mutated into a
  stream of ``budget`` unique invalid-program tests (syntax, lexical and
  semantic mutants).
* **Mutation baseline arm** executes all ``budget`` mutation tests.
* **AI-guided arm** executes the *same first* ``ai_seed_tests`` mutation
  tests, then spends the remaining ``budget - ai_seed_tests`` executions on
  AI-generated tests produced in feedback rounds (each round sees only the
  compiler results of tests that arm has already executed).

Both arms therefore run exactly ``budget`` tests, share an identical prefix, and
differ only in how the remaining tests are produced. All metrics are computed
over everything an arm executed. Duplicates are discarded before execution and
reported. If the AI service is unavailable, or an AI arm ends under budget, the
trial is reported as incomplete and excluded from the comparison; nothing is
imputed or invented.

With the default seeds the experiment is reproducible for the mutation arm and
the shared prefix; AI output is non-deterministic, so repeat trials report mean
and spread rather than a single number.
"""

import argparse
import json
import math
import os
import statistics
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.ai_generator import AIGenerator  # noqa: E402
from generator.generator import GrammarGenerator  # noqa: E402
from generator.mutations import MutationEngine  # noqa: E402
from harness.ai_loop import run_ai_loop  # noqa: E402
from harness.analysis import (  # noqa: E402
    candidate_bugs,
    category_counts,
    collect_patterns,
    discovery_curve,
)
from harness.dedupe import canonical_form  # noqa: E402
from harness.execution import new_trackers, run_tests  # noqa: E402
from harness.reporting import (  # noqa: E402
    PROJECT_ROOT,
    SCHEMA_VERSION,
    build_metadata,
    create_run_dir,
    sub_seed,
    utc_now,
    write_json,
)

HISTORICAL_PATH = PROJECT_ROOT / "reports" / "legacy" / "prototype_reported_results.json"
AGGREGATED_METRICS = [
    "tests_executed",
    "unique_error_patterns",
    "unique_error_patterns_raw",
    "patterns_per_test",
    "new_patterns_after_seed",
    "duplicate_rate",
    "potential_compiler_bugs",
]


@dataclass
class EvaluationConfig:
    budget: int = 60
    ai_seed_tests: int = 20
    round_size: int = 10
    max_extra_rounds: int = 2
    trials: int = 3
    base_seed: int = 42
    semantic_ratio: float = 0.2
    valid_pool: int = 30
    ai_enabled: bool = True
    output_dir: Optional[str] = None


def _configure_console():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")


def describe(values):
    """Mean and sample standard deviation (``None`` for fewer than 2 values)."""
    values = list(values)
    if not values:
        return {"n": 0, "mean": None, "stdev": None, "min": None, "max": None, "values": []}
    return {
        "n": len(values),
        "mean": round(statistics.mean(values), 4),
        "stdev": round(statistics.stdev(values), 4) if len(values) > 1 else None,
        "min": min(values),
        "max": max(values),
        "values": values,
    }


def arm_metrics(results, seed_count):
    n = len(results)
    patterns = collect_patterns(results)
    seed_patterns = collect_patterns(results[:seed_count])
    unique_programs = len({canonical_form(r["code"]) for r in results})
    bugs = candidate_bugs(results)
    return {
        "tests_executed": n,
        "unique_programs": unique_programs,
        "duplicate_rate": round((n - unique_programs) / n, 4) if n else 0.0,
        "unique_error_patterns": len(patterns),
        "unique_error_patterns_raw": len(collect_patterns(results, normalized=False)),
        "patterns_per_test": round(len(patterns) / n, 4) if n else 0.0,
        "new_patterns_after_seed": len(patterns - seed_patterns),
        "error_categories": category_counts(results),
        "potential_compiler_bugs": len(bugs),
        "potential_bug_ids": [r["id"] for r in bugs],
        "expectation_mismatches": sum(1 for r in results if not r["expectation_matched"]),
        "discovery_curve": discovery_curve(results),
        "patterns": sorted(patterns),
    }


def run_trial(index, seed, config, ai, ai_ready, echo):
    pool = GrammarGenerator(seed=sub_seed(seed, "valid")).generate_unique_programs(config.valid_pool)
    engine = MutationEngine(seed=sub_seed(seed, "mutation"))
    baseline_tests = engine.generate(pool, config.budget, config.semantic_ratio)

    dups, pats = new_trackers()
    baseline_results = run_tests(baseline_tests, dups, pats)
    baseline = arm_metrics(baseline_results, config.ai_seed_tests)

    trial = {
        "trial": index,
        "seed": seed,
        "baseline": baseline,
        "ai_guided": None,
        "comparison": None,
        "status": "AI_NOT_RUN",
        "notes": [],
    }
    details = {"baseline": baseline_results, "ai_guided": []}
    if len(baseline_results) < config.budget:
        trial["notes"].append(
            f"mutation baseline executed {len(baseline_results)}/{config.budget} tests "
            "(bounded duplicate-free generation fell short)"
        )

    if not (config.ai_enabled and ai_ready):
        trial["notes"].append("AI-guided arm not run: AI unavailable or disabled")
        return trial, details

    ai_budget = config.budget - config.ai_seed_tests
    dups2, pats2 = new_trackers()
    seed_results = run_tests(baseline_tests[: config.ai_seed_tests], dups2, pats2)
    loop = run_ai_loop(
        ai,
        seed_results,
        budget=ai_budget,
        round_size=config.round_size,
        max_rounds=math.ceil(ai_budget / config.round_size) + config.max_extra_rounds,
        duplicates=dups2,
        patterns=pats2,
        echo=echo,
    )
    ai_arm = seed_results + loop["results"]
    metrics = arm_metrics(ai_arm, config.ai_seed_tests)
    metrics.update(
        {
            "seed_tests": len(seed_results),
            "ai_tests_executed": len(loop["results"]),
            "ai_status": loop["status"],
            "ai_reason": loop["reason"],
            "rounds": loop["rounds"],
            "ai_duplicates_discarded": sum(r["duplicates_discarded"] for r in loop["rounds"]),
        }
    )
    trial["ai_guided"] = metrics
    details["ai_guided"] = ai_arm

    complete = len(ai_arm) == config.budget and len(baseline_results) == config.budget
    if loop["status"] in ("SKIPPED", "FAILED"):
        trial["status"] = "AI_UNAVAILABLE"
    elif not complete:
        trial["status"] = "INCOMPLETE"
        trial["notes"].append(
            f"AI arm executed {len(ai_arm)}/{config.budget} tests (status {loop['status']})"
        )
    else:
        trial["status"] = "COMPLETE"

    if trial["status"] == "COMPLETE":
        bp, ap = set(baseline["patterns"]), set(metrics["patterns"])
        trial["comparison"] = {
            "ai_only_patterns": sorted(ap - bp),
            "baseline_only_patterns": sorted(bp - ap),
            "shared_patterns": len(ap & bp),
            "difference_ai_minus_baseline": {
                k: round(metrics[k] - baseline[k], 4)
                for k in ("unique_error_patterns", "patterns_per_test", "new_patterns_after_seed")
            },
        }
    return trial, details


def aggregate(trials):
    complete = [t for t in trials if t["status"] == "COMPLETE"]
    result = {
        "trials_total": len(trials),
        "trials_complete": len(complete),
        "incomplete_trials": [
            {"trial": t["trial"], "seed": t["seed"], "status": t["status"], "notes": t["notes"]}
            for t in trials
            if t["status"] != "COMPLETE"
        ],
        "baseline_all_trials": {m: describe(t["baseline"][m] for t in trials) for m in AGGREGATED_METRICS},
        "comparison": None,
    }
    if complete:
        result["comparison"] = {
            "baseline": {m: describe(t["baseline"][m] for t in complete) for m in AGGREGATED_METRICS},
            "ai_guided": {m: describe(t["ai_guided"][m] for t in complete) for m in AGGREGATED_METRICS},
            "paired_difference_ai_minus_baseline": {
                m: describe(t["comparison"]["difference_ai_minus_baseline"][m] for t in complete)
                for m in ("unique_error_patterns", "patterns_per_test", "new_patterns_after_seed")
            },
            "trials_ai_ahead_on_unique_patterns": sum(
                1 for t in complete if t["comparison"]["difference_ai_minus_baseline"]["unique_error_patterns"] > 0
            ),
            "trials_tied": sum(
                1 for t in complete if t["comparison"]["difference_ai_minus_baseline"]["unique_error_patterns"] == 0
            ),
        }
    return result


def _fmt(stat):
    if stat["n"] == 0:
        return "n/a"
    if stat["stdev"] is None:
        return f"{stat['mean']:.3f}".rstrip("0").rstrip(".")
    return f"{stat['mean']:.3f} +/- {stat['stdev']:.3f}".replace(".000", "")


def print_report(echo, config, trials, agg, ai_note):
    echo()
    echo("========================================")
    echo("       COMPILERGUARD EVALUATION")
    echo("========================================")
    echo(f"Test budget per arm : {config.budget}")
    echo(f"Design              : baseline = {config.budget} mutation tests; "
         f"AI arm = same first {config.ai_seed_tests} + up to "
         f"{config.budget - config.ai_seed_tests} AI tests")
    echo(f"Trials requested    : {config.trials} (seeds {config.base_seed}..{config.base_seed + config.trials - 1})")
    echo()
    echo("Per-trial status:")
    for t in trials:
        ai = t["ai_guided"]
        line = f"  trial {t['trial']} seed {t['seed']}: {t['status']:<14} baseline patterns={t['baseline']['unique_error_patterns']}"
        if ai:
            line += f", AI-arm patterns={ai['unique_error_patterns']} ({ai['tests_executed']}/{config.budget} executed)"
        echo(line)
        for note in t["notes"]:
            echo(f"      note: {note}")

    echo()
    if agg["comparison"] is None:
        echo("AI-GUIDED ARM: NOT COMPLETED. No baseline-vs-AI comparison is reported.")
        echo(f"Reason: {ai_note}")
        echo()
        echo("Mutation baseline only (all trials):")
        for m in ("tests_executed", "unique_error_patterns", "patterns_per_test", "potential_compiler_bugs"):
            echo(f"  {m:<26} {_fmt(agg['baseline_all_trials'][m])}")
    else:
        cmp_ = agg["comparison"]
        echo(f"Comparison over {agg['trials_complete']} complete trial(s)  (mean +/- sample stdev; stdev needs >= 2 trials)")
        echo(f"{'Metric':<28}{'Mutation baseline':<24}{'AI-guided'}")
        labels = {
            "tests_executed": "Tests executed",
            "unique_error_patterns": "Unique error patterns",
            "patterns_per_test": "Patterns per test",
            "new_patterns_after_seed": "New patterns after seed",
            "duplicate_rate": "Duplicate-test rate",
            "potential_compiler_bugs": "Potential compiler bugs",
        }
        for m, label in labels.items():
            echo(f"{label:<28}{_fmt(cmp_['baseline'][m]):<24}{_fmt(cmp_['ai_guided'][m])}")
        echo()
        echo(f"Paired difference (AI - baseline), unique patterns: "
             f"{_fmt(cmp_['paired_difference_ai_minus_baseline']['unique_error_patterns'])}")
        echo(f"AI ahead in {cmp_['trials_ai_ahead_on_unique_patterns']}, tied in {cmp_['trials_tied']}, "
             f"behind in {agg['trials_complete'] - cmp_['trials_ai_ahead_on_unique_patterns'] - cmp_['trials_tied']} "
             f"of {agg['trials_complete']} trials")
        echo("Interpretation: small samples; this is descriptive, not a significance test.")
        for t in trials:
            if t["comparison"]:
                echo(f"\nTrial {t['trial']} AI-only patterns ({len(t['comparison']['ai_only_patterns'])}):")
                for p in t["comparison"]["ai_only_patterns"]:
                    echo(f"  {p}")

    if HISTORICAL_PATH.exists():
        hist = json.loads(HISTORICAL_PATH.read_text(encoding="utf-8"))
        echo()
        echo("Historical prototype result (REPORTED BY AUTHOR, NOT VERIFIED, raw data unavailable;")
        echo("different pattern definition and arm accounting - not comparable to the table above):")
        h = hist["reported"]
        echo(f"  budget {h['test_budget_per_approach']}: random patterns {h['random']['unique_error_patterns']}, "
             f"AI-guided patterns {h['ai_guided']['unique_error_patterns']}, "
             f"AI-only patterns {h['ai_only_error_patterns']}")


def run_evaluation(config, ai_generator=None, echo=print):
    echo = echo or (lambda *_: None)
    started = utc_now()
    run_dir = create_run_dir(config.output_dir, label="evaluation", seed=config.base_seed)
    run_id = run_dir.name

    ai = ai_generator if ai_generator is not None else AIGenerator()
    ai_ready, ai_reason = ai.availability() if config.ai_enabled else (False, "disabled with --no-ai")
    if not ai_ready:
        echo(f"AI-guided arm will be skipped: {ai_reason}")

    trials, all_details = [], []
    for i in range(config.trials):
        seed = config.base_seed + i
        echo(f"Running trial {i + 1}/{config.trials} (seed {seed}) ...")
        trial, details = run_trial(i + 1, seed, config, ai, ai_ready, echo)
        trials.append(trial)
        all_details.append({"trial": i + 1, "seed": seed, **details})

    agg = aggregate(trials)
    ai_note = ai_reason or "AI arm incomplete in every trial (see per-trial notes)"
    print_report(echo, config, trials, agg, ai_note)

    finished = utc_now()
    ai_info = {
        "enabled": config.ai_enabled,
        "available": bool(ai_ready),
        "reason_unavailable": None if ai_ready else ai_reason,
        "model": getattr(ai, "model", None),
        "rounds_completed": sum(
            1 for t in trials if t["ai_guided"] for r in t["ai_guided"]["rounds"] if r["status"] == "OK"
        ),
    }
    summary = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "design": {
            "budget_per_arm": config.budget,
            "ai_seed_tests": config.ai_seed_tests,
            "ai_test_budget": config.budget - config.ai_seed_tests,
            "round_size": config.round_size,
            "paired_prefix": True,
            "pattern_definition": "TYPE: message with variable names and characters replaced by placeholders",
            "bug_definition": "compiler result disagrees with the independent oracle (candidate only)",
        },
        "ai_available": bool(ai_ready),
        "trials": trials,
        "aggregate": agg,
    }
    if HISTORICAL_PATH.exists():
        summary["historical_reference"] = json.loads(HISTORICAL_PATH.read_text(encoding="utf-8"))

    write_json(run_dir / "evaluation_summary.json", summary)
    write_json(
        run_dir / "evaluation_details.json",
        {"schema_version": SCHEMA_VERSION, "run_id": run_id, "trials": all_details},
    )
    write_json(
        run_dir / "experiment_metadata.json",
        build_metadata("evaluation", run_id, asdict(config), ai_info, started, finished),
    )
    echo()
    echo(f"Reports written to: {run_dir}")
    summary["report_dir"] = str(run_dir)
    return summary


def main(argv=None):
    _configure_console()
    p = argparse.ArgumentParser(description="Equal-budget mutation vs AI-guided evaluation.")
    p.add_argument("--budget", type=int, default=60, help="tests executed per approach")
    p.add_argument("--ai-seed-tests", type=int, default=20, help="mutation tests shared by both arms")
    p.add_argument("--round-size", type=int, default=10, help="AI tests requested per round")
    p.add_argument("--trials", type=int, default=3)
    p.add_argument("--seed", type=int, default=42, dest="base_seed", help="first trial seed")
    p.add_argument("--semantic-ratio", type=float, default=0.2)
    p.add_argument("--no-ai", action="store_true")
    p.add_argument("--output-dir", default=None)
    args = p.parse_args(argv)
    if not 0 < args.ai_seed_tests < args.budget:
        p.error("--ai-seed-tests must be between 1 and budget-1")

    config = EvaluationConfig(
        budget=args.budget,
        ai_seed_tests=args.ai_seed_tests,
        round_size=args.round_size,
        trials=args.trials,
        base_seed=args.base_seed,
        semantic_ratio=args.semantic_ratio,
        ai_enabled=not args.no_ai,
        output_dir=args.output_dir,
    )
    run_evaluation(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
