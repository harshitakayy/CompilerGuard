"""Equal-budget experiment over three arms.

* blind     - smart grammar-aware mutation, operators scheduled round-robin
              (no use of compiler feedback);
* feedback  - same mutation operators, but their selection adapts to compiler
              feedback (novel error patterns, production coverage, AST shapes,
              new compiler lines, bug signals). Needs no API key;
* ai        - an LLM receives grammar + structured compiler feedback each round
              and proposes new programs (skipped, and reported as such, when no
              API access is available).

All arms execute exactly ``budget`` tests and share the same first
``seed_tests`` (paired prefix), so differences come from the remaining tests.
"""

import math
from collections import Counter
from dataclasses import asdict, dataclass

from grammarkit.mutate import SmartMutator
from harness.ai_loop import run_ai_loop
from harness.analysis import PatternTracker, category_counts
from harness.dedupe import DuplicateTracker
from harness.execution import run_test
from harness.reporting import sub_seed

from .metrics import ArmTracker, describe

ARM_LABELS = {"blind": "Mutation (blind)", "feedback": "Mutation + compiler feedback", "ai": "AI-guided"}
METRICS = ["unique_error_patterns", "bug_signals", "production_coverage_pct", "ast_unique_shapes",
           "ast_unique_edges", "path_coverage_pct", "new_patterns_per_test", "novel_tests"]


@dataclass
class LabConfig:
    budget: int = 60
    seed_tests: int = 20
    batch: int = 10
    trials: int = 3
    seed: int = 42
    parents: int = 30
    arms: tuple = ("blind", "feedback", "ai")
    ai_extra_rounds: int = 2


class AdaptiveSelector:
    """Multiplicative weights over mutation operators, driven by novelty."""

    EXPLORE = 0.3  # share of probability mass kept uniform (epsilon-greedy style)

    def __init__(self, ops):
        self.weights = {o: 1.0 for o in ops}

    def probabilities(self):
        total, n = sum(self.weights.values()), len(self.weights)
        return {o: (1 - self.EXPLORE) * w / total + self.EXPLORE / n for o, w in self.weights.items()}

    def reward(self, op, score):
        w = self.weights.get(op, 1.0)
        self.weights[op] = min(12.0, max(0.25, 0.8 * w + 0.5 * score + (0.2 if score > 0 else 0.0)))


def _compact(rec):
    r = rec["compiler_response"]
    prov = rec.get("provenance", {})
    return {"id": rec["id"], "code": rec["code"], "source": rec["source"], "operator": prov.get("operator"),
            "intent": prov.get("intent"), "expected_status": rec["expected_status"], "actual_status": rec["actual_status"],
            "outcome": rec["outcome"], "pattern": rec["error_pattern"], "signal": rec["potential_compiler_bug"],
            "reasons": rec["bug_reasons"], "oracle": {k: rec["oracle"].get(k) for k in ("status", "type", "line", "column")},
            "response": {k: r.get(k) for k in ("status", "type", "line", "column", "message")}, "novelty": rec.get("novelty")}


class Arm:
    def __init__(self, target):
        self.tracker, self.dups, self.records = ArmTracker(target), DuplicateTracker(), []
        self.target = target

    def run(self, tests):
        out = []
        for t in tests:
            rec = run_test(t, self.dups, None, self.target)
            _, lines = self.target.compile_traced(t["code"])
            rec["novelty"] = self.tracker.observe(rec, lines)
            out.append(rec)
        self.records.extend(out)
        return out

    def result(self, key, status="COMPLETE", reason=None, extra=None):
        summary = self.tracker.summary(len(self.records), category_counts(self.records) if self.records else {})
        summary["duplicate_rate"] = round(sum(1 for r in self.records if r["duplicate_of"]) / len(self.records), 4) if self.records else 0.0
        out = {"arm": key, "label": ARM_LABELS[key], "status": status, "reason": reason, "summary": summary,
               "tests": [_compact(r) for r in self.records]}
        if extra:
            out.update(extra)
        return out


def _flat_metrics(summary):
    return {"unique_error_patterns": summary["unique_error_patterns"], "bug_signals": summary["bug_signals"],
            "production_coverage_pct": summary["production_coverage"]["percent"], "ast_unique_shapes": summary["ast"]["unique_shapes"],
            "ast_unique_edges": summary["ast"]["unique_edges"], "path_coverage_pct": summary["path_coverage"]["percent"],
            "new_patterns_per_test": summary["new_patterns_per_test"], "novel_tests": summary["novel_tests"]}


def run_trial(target, cfg, seed, ai, say):
    parents = target.valid_programs(cfg.parents, seed)
    if not parents:
        raise ValueError("The grammar produced no valid sample programs; check its rules.")
    parent_keys = {target.canonical(p["code"]) for p in parents}
    blind_tests = SmartMutator(target, sub_seed(seed, "blind")).generate(parents, cfg.budget, exclude=parent_keys)
    prefix = blind_tests[: cfg.seed_tests]
    arms = {}

    if "blind" in cfg.arms:
        say("blind: executing mutation tests")
        arm = Arm(target)
        arm.run(blind_tests)
        arms["blind"] = arm.result("blind", "COMPLETE" if len(arm.records) >= cfg.budget else "INCOMPLETE")

    if "feedback" in cfg.arms:
        say("feedback: adaptive mutation")
        arm, mut = Arm(target), SmartMutator(target, sub_seed(seed, "feedback"))
        sel = AdaptiveSelector(mut.operators)
        for rec in arm.run(prefix):
            sel.reward(rec["provenance"]["operator"], rec["novelty"]["score"])
        keys = parent_keys | {target.canonical(t["code"]) for t in prefix}
        while len(arm.records) < cfg.budget:
            k = min(cfg.batch, cfg.budget - len(arm.records))
            batch = mut.generate(parents, k, exclude=keys, weights=sel.probabilities(), id_prefix="fb", start_index=len(arm.records) + 1)
            if not batch:
                break
            keys |= {target.canonical(t["code"]) for t in batch}
            for rec in arm.run(batch):
                sel.reward(rec["provenance"]["operator"], rec["novelty"]["score"])
        arms["feedback"] = arm.result("feedback", "COMPLETE" if len(arm.records) >= cfg.budget else "INCOMPLETE",
                                      extra={"operator_weights": {k: round(v, 2) for k, v in sorted(sel.weights.items(), key=lambda kv: -kv[1])}})

    if "ai" in cfg.arms:
        ok, why = ai.availability() if ai is not None else (False, "AI disabled")
        if not ok:
            arms["ai"] = {"arm": "ai", "label": ARM_LABELS["ai"], "status": "NOT_RUN", "reason": why, "summary": None, "tests": []}
        else:
            say("ai: feedback rounds")
            arm = Arm(target)
            arm.run(prefix)
            ai_budget = cfg.budget - len(prefix)
            loop = run_ai_loop(ai, arm.records, ai_budget, cfg.batch, math.ceil(ai_budget / cfg.batch) + cfg.ai_extra_rounds,
                               arm.dups, PatternTracker(), target=target, runner=arm.run)
            # run_ai_loop appends its own results through ``runner``; do not add them twice
            status = "COMPLETE" if len(arm.records) >= cfg.budget else ("NOT_RUN" if loop["status"] in ("SKIPPED", "FAILED") and len(arm.records) <= len(prefix) else "INCOMPLETE")
            arms["ai"] = arm.result("ai", status, loop["reason"], extra={"ai": {"status": loop["status"], "rounds": loop["rounds"], "tests_requested": ai_budget}})
            if status == "NOT_RUN":
                arms["ai"].update({"summary": None, "tests": []})
                arms["ai"]["reason"] = loop["reason"] or "AI generation failed in the first round"
    return {"seed": seed, "parents": len(parents), "arms": arms}


def aggregate(trials, arm_keys):
    out = {}
    for key in arm_keys:
        done = [t["arms"][key] for t in trials if key in t["arms"] and t["arms"][key]["status"] == "COMPLETE"]
        out[key] = {"label": ARM_LABELS[key], "trials_complete": len(done), "trials_total": len(trials),
                    "metrics": {m: describe(_flat_metrics(a["summary"])[m] for a in done) for m in METRICS} if done else None}
    base = out.get("blind", {}).get("metrics")
    for key, entry in out.items():
        if base and entry["metrics"] and key != "blind":
            entry["delta_vs_blind"] = {m: round(entry["metrics"][m]["mean"] - base[m]["mean"], 3) for m in METRICS}
    return out


def run_lab(target, cfg, ai=None, progress=None):
    def say(msg, pct=None):
        if progress:
            progress(msg, pct)

    cfg.seed_tests = max(1, min(cfg.seed_tests, cfg.budget - 1))
    trials = []
    for i in range(cfg.trials):
        say(f"Trial {i + 1}/{cfg.trials} (seed {cfg.seed + i})", 100 * i // cfg.trials)
        trials.append(run_trial(target, cfg, cfg.seed + i, ai, lambda m, i=i: say(f"Trial {i + 1}: {m}", None)))
    say("Aggregating", 98)
    return {"target": target.id, "target_name": target.name, "config": asdict(cfg),
            "design": {"budget_per_arm": cfg.budget, "shared_prefix": cfg.seed_tests, "batch": cfg.batch,
                       "bug_signal": "compiler result disagrees with the independent Earley/reference oracle (candidate only)",
                       "production_coverage": "BNF productions completed in the Earley chart (counted even for rejected programs)",
                       "ast_diversity": "unique depth-4 parse-tree shapes and unique parent-child production edges, over accepted programs",
                       "path_coverage": "executed lines / executable lines of the instrumented compiler modules (sys.settrace)"},
            "trials": trials, "aggregate": aggregate(trials, cfg.arms),
            "grammar": {"productions": len(target.grammar.alts), "rules": len(target.grammar.source_rules)}}
