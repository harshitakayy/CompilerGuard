"""End-to-end CompilerGuard pipeline.

    python tests/test_runner.py [--seed 42] [--valid 20] [--mutations 30]
                                [--ai-rounds 3] [--ai-per-round 5] [--no-ai]

Steps: generate valid programs -> execute -> generate controlled mutants ->
execute -> collect and group structured compiler errors -> (optional) AI-guided
rounds fed by those errors -> final statistics. Every run writes its reports to
a fresh directory under ``reports/runs/`` and never overwrites earlier runs.

The pipeline runs to completion without an API key; AI generation is then
reported as SKIPPED and no AI tests are recorded.
"""

import argparse
import os
import sys
from dataclasses import asdict, dataclass
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.ai_generator import AIGenerator  # noqa: E402
from generator.generator import GrammarGenerator  # noqa: E402
from generator.mutations import MutationEngine  # noqa: E402
from harness.ai_loop import run_ai_loop  # noqa: E402
from harness.analysis import (  # noqa: E402
    candidate_bugs,
    category_counts,
    summarize_patterns,
    summarize_results,
)
from harness.execution import new_trackers, run_tests  # noqa: E402
from harness.reporting import (  # noqa: E402
    SCHEMA_VERSION,
    build_metadata,
    create_run_dir,
    sub_seed,
    utc_now,
    write_json,
)


@dataclass
class PipelineConfig:
    seed: int = 42
    valid_count: int = 30
    mutation_count: int = 100
    semantic_ratio: float = 0.2
    ai_rounds: int = 3
    ai_per_round: int = 5
    ai_enabled: bool = True
    output_dir: Optional[str] = None


def _configure_console():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")


def _section(echo, title):
    echo()
    echo(f"========== {title} ==========")


def _report_block(run_id, category, results, extra=None):
    payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "category": category,
        "summary": summarize_results(results),
        "results": results,
    }
    if extra:
        payload.update(extra)
    return payload


def _print_outcomes(echo, results):
    s = summarize_results(results)
    echo(f"Total tests            : {s['total']}")
    echo(f"As expected            : {s['expectation_matched']}")
    echo(f"Different from expected: {s['expectation_mismatched']}")
    echo(f"Compiler outcomes      : {s['compiler_outcomes']}")
    echo(f"Duplicates             : {s['duplicate_tests']}")


def run_pipeline(config, ai_generator=None, echo=print):
    """Execute the full pipeline and return a summary dictionary."""
    echo = echo or (lambda *_: None)
    started = utc_now()
    run_dir = create_run_dir(config.output_dir, label="pipeline", seed=config.seed)
    run_id = run_dir.name
    duplicates, patterns = new_trackers()

    echo()
    echo("========================================")
    echo("            COMPILERGUARD")
    echo("   AI-GUIDED COMPILER TESTING PIPELINE")
    echo("========================================")
    echo(f"Run id : {run_id}")
    echo(f"Seed   : {config.seed}")

    # 1-2. Valid programs.
    generator = GrammarGenerator(seed=sub_seed(config.seed, "valid"))
    valid_tests = generator.generate_unique_programs(config.valid_count)
    valid_results = run_tests(valid_tests, duplicates, patterns)
    _section(echo, "VALID TESTS (grammar-based generation)")
    _print_outcomes(echo, valid_results)
    echo("Expectation: compiler accepts every valid program")

    # 3-4. Mutants.
    engine = MutationEngine(seed=sub_seed(config.seed, "mutation"))
    mutation_tests = engine.generate(
        valid_tests,
        config.mutation_count,
        semantic_ratio=config.semantic_ratio,
        exclude=duplicates.keys(),
    )
    mutation_results = run_tests(mutation_tests, duplicates, patterns)
    _section(echo, "MUTATION TESTS (controlled mutation)")
    _print_outcomes(echo, mutation_results)
    operators = {}
    for r in mutation_results:
        op = r["provenance"]["operator"]
        operators[op] = operators.get(op, 0) + 1
    echo(f"Operators used         : {len(operators)}")

    # 5-6. Error analysis of what the compiler reported so far.
    executed = valid_results + mutation_results
    error_patterns = summarize_patterns(executed)

    # 7-11. AI-guided rounds.
    ai = ai_generator if ai_generator is not None else AIGenerator()
    _section(echo, "AI-GUIDED TESTS")
    if not config.ai_enabled:
        loop = {"status": "SKIPPED", "reason": "disabled with --no-ai", "results": [], "rounds": [], "budget_met": False}
    else:
        echo(f"Error patterns available as feedback: {len(error_patterns)}")
        loop = run_ai_loop(
            ai,
            executed,
            budget=config.ai_rounds * config.ai_per_round,
            round_size=config.ai_per_round,
            max_rounds=config.ai_rounds,
            duplicates=duplicates,
            patterns=patterns,
            echo=echo,
        )
    ai_results = loop["results"]
    if loop["status"] == "SKIPPED":
        echo(f"AI generation SKIPPED: {loop['reason']}")
        echo("No AI tests were run; no AI results are reported.")
    else:
        echo(f"AI status              : {loop['status']}"
             + (f" ({loop['reason']})" if loop["reason"] else ""))
        _print_outcomes(echo, ai_results)

    # 8, 12. Final analysis.
    everything = valid_results + mutation_results + ai_results
    bugs = candidate_bugs(everything)
    revised = [r for r in everything if r["adjudication"] == "EXPECTATION_REVISED_BY_ORACLE"]
    all_patterns = summarize_patterns(everything)
    _section(echo, "ERROR ANALYSIS")
    echo(f"Distinct error patterns: {len(all_patterns)}")
    for entry in all_patterns:
        echo(f"  {entry['count']:>3} x {entry['pattern']}")
    echo(f"Potential compiler bugs (candidates, need investigation): {len(bugs)}")
    for r in bugs:
        echo(f"  {r['id']}: {r['code']!r} -> compiler {r['compiler_response']} | oracle {r['oracle']} {r['bug_reasons']}")
    echo(f"Tests whose expectation the oracle revised (equivalent mutant / generator defect): {len(revised)}")

    summary = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "totals": {
            "valid": len(valid_results),
            "mutation": len(mutation_results),
            "ai": len(ai_results),
            "all": len(everything),
        },
        "valid_accepted": sum(1 for r in valid_results if r["actual_status"] == "PASS"),
        "mutants_rejected": sum(1 for r in mutation_results if r["actual_status"] == "FAIL"),
        "unique_error_patterns": len(all_patterns),
        "potential_compiler_bugs": len(bugs),
        "intent_revised_by_oracle": len(revised),
        "ai_status": loop["status"],
        "ai_rounds_completed": sum(1 for r in loop["rounds"] if r["status"] == "OK"),
        "duplicate_tests": sum(1 for r in everything if r["duplicate_of"]),
    }

    _section(echo, "FINAL STATISTICS")
    echo(f"Valid programs accepted : {summary['valid_accepted']}/{summary['totals']['valid']}")
    echo(f"Mutants rejected        : {summary['mutants_rejected']}/{summary['totals']['mutation']}")
    echo(f"AI tests executed       : {summary['totals']['ai']} (AI status: {summary['ai_status']})")
    echo(f"Unique error patterns   : {summary['unique_error_patterns']}")
    echo(f"Potential compiler bugs : {summary['potential_compiler_bugs']} (candidates only)")

    # Reports.
    finished = utc_now()
    ai_info = {
        "enabled": config.ai_enabled,
        "status": loop["status"],
        "reason": loop["reason"],
        "model": getattr(ai, "model", None),
        "rounds_completed": summary["ai_rounds_completed"],
        "rounds": loop["rounds"],
    }
    write_json(run_dir / "valid_results.json", _report_block(run_id, "valid", valid_results))
    write_json(
        run_dir / "invalid_results.json",
        _report_block(run_id, "invalid", mutation_results, {"mutation_shortfall": engine.shortfall}),
    )
    write_json(
        run_dir / "ai_results.json",
        _report_block(run_id, "ai_guided", ai_results, {"ai": ai_info}),
    )
    write_json(
        run_dir / "error_statistics.json",
        {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "error_patterns": all_patterns,
            "compiler_outcomes": category_counts(everything),
            "per_category": {
                "valid": category_counts(valid_results),
                "mutation": category_counts(mutation_results),
                "ai": category_counts(ai_results),
            },
            "potential_compiler_bugs": [
                {k: r[k] for k in ("id", "code", "compiler_response", "oracle", "bug_reasons")}
                for r in bugs
            ],
        },
    )
    write_json(run_dir / "pipeline_summary.json", summary)
    write_json(
        run_dir / "experiment_metadata.json",
        build_metadata("pipeline", run_id, asdict(config), ai_info, started, finished),
    )
    echo()
    echo(f"Reports written to: {run_dir}")
    summary["report_dir"] = str(run_dir)
    return summary


def main(argv=None):
    _configure_console()
    p = argparse.ArgumentParser(description="Run the CompilerGuard testing pipeline.")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--valid", type=int, default=30, dest="valid_count")
    p.add_argument("--mutations", type=int, default=100, dest="mutation_count")
    p.add_argument("--semantic-ratio", type=float, default=0.2)
    p.add_argument("--ai-rounds", type=int, default=3)
    p.add_argument("--ai-per-round", type=int, default=5)
    p.add_argument("--no-ai", action="store_true", help="skip AI-guided generation")
    p.add_argument("--output-dir", default=None, help="base directory for run folders")
    p.add_argument("--strict", action="store_true", help="exit 1 if candidate bugs are found")
    args = p.parse_args(argv)

    config = PipelineConfig(
        seed=args.seed,
        valid_count=args.valid_count,
        mutation_count=args.mutation_count,
        semantic_ratio=args.semantic_ratio,
        ai_rounds=args.ai_rounds,
        ai_per_round=args.ai_per_round,
        ai_enabled=not args.no_ai,
        output_dir=args.output_dir,
    )
    summary = run_pipeline(config)
    return 1 if args.strict and summary["potential_compiler_bugs"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
