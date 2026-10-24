# Changes

## Version 2: web laboratory, C++ subset, custom grammars
* `server.py` + `web/` - standard-library backend and a luxury-styled front end covering every feature (language choice, grammar editor, compile, generate, experiment dashboard).
* `grammarkit/` - EBNF grammar parser with analysis and line-numbered errors, generic lexer, Earley oracle, packrat (PEG) parser under test, coverage-directed generator, 22 grammar-aware mutation operators.
* `grammars/` - CG-Lang, a 187-production C++ subset, Calculator, JSON-like and an ordered-choice hazard demo.
* `lab/` - three-approach equal-budget experiment (blind mutation, feedback-steered mutation, AI-guided) with metrics: unique error patterns, bug signals, production coverage, AST diversity, path coverage, per-test novelty.
* AI module accepts any grammar and an optional in-memory per-run key; the key is never stored or logged.
* Defaults raised: pipeline 30 valid + 100 mutants, evaluation budget 60.
* Tests: 173 -> 250 (grammar engine, differential PEG-vs-Earley checks, lab, API, frontend/element-id consistency).

# Changes in this upgrade

## Defects fixed in the original code
* `compiler/semantic.py` - duplicated lines (introduced by the last commit) caused an `IndentationError`; nothing could be imported.
* `ai/ai_generator.py` - the OpenAI client was created at import time, so the whole project crashed without an API key.
* `tests/evaluation.py` - called `generate_targeted_tests` with 3 arguments; the function accepted 2.
* `compiler/lexer.py` - used `str.isdigit()/isalpha()`, so non-ASCII input (`x = ²;`, `é = 1;`) compiled successfully.
* Deeply nested parentheses could raise `RecursionError`; they now give a structured syntax error.
* Evaluation counted only the AI arm's AI tests (not the 45 seed tests that fed it) and pattern identity included variable names.

## New
* `harness/` - independent reference oracle, execution/classification, error analysis, dedupe, reporting, shared AI loop.
* `generator/` - seeded, bounded, duplicate-free grammar generator; 30 mutation operators with intent tracking.
* `ai/` - graceful, validated, secret-safe AI generation using the Responses API with a JSON schema.
* `tests/test_runner.py`, `tests/evaluation.py` - rewritten pipeline and equal-budget, multi-trial evaluation.
* 173 offline pytest tests; legacy reports moved to `reports/legacy/`; line endings normalised to LF; comments rewritten in English.
