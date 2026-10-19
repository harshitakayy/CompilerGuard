# CompilerGuard
AI-guided, grammar-based compiler fuzzing with a web dashboard.

## Run
```
pip install -r requirements.txt
python main.py web          # dashboard at http://localhost:5000
python main.py fuzz         # terminal campaign (add --fault mod_wrong to plant a bug)
python main.py ai           # AI-guided loop in terminal
python -m unittest discover -s tests -v
```
On Replit: press Run (uses `.replit`). For a real LLM add a Secret: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` or `GEMINI_API_KEY`. Without a key an offline heuristic generator is used (the UI says which one ran).

## What it does
- **CG-Lang compiler** (`compiler/`): lexer, recursive-descent parser, semantic analysis, interpreter. Variables, + - * / %, unary minus, comparisons, `print`, `if/else`, `while`, comments. Errors: lexical, syntax, semantic, runtime, limit (line/column included).
- **Grammar-based generator** (`generator/generator.py`): valid programs derived from the grammar.
- **Mutation generator** (`generator/mutations.py`): 21 operators; 16 *guarantee* an invalid program, so acceptance = bug.
- **Test oracle** (`fuzzer/reference.py`): independent reference implementation for differential testing (wrong output = bug).
- **Fuzz engine** (`fuzzer/engine.py`): valid + mutants + 21 stress cases + coverage-guided feedback; classifies crashes, false accepts, false rejects, wrong outputs.
- **Test-case minimizer** (`fuzzer/minimizer.py`): shrinks any bug to a minimal reproducer.
- **AI engine** (`ai/ai_generator.py`): error patterns -> LLM -> targeted tests -> compiler -> new patterns, multiple rounds.
- **Web dashboard** (`web/`): playground, fuzz campaign with per-test ribbon and coverage curve, AI loop, downloadable report.
- **Fault injection**: 6 planted bugs (see `compiler.FAULTS`) prove the fuzzer really finds bugs.

## Results (seed 1, 30 valid + 150 mutants)
Clean compiler: 273 programs, 0 bugs, 51 distinct outcomes, 32 rules covered.
Each planted fault is detected (unit-tested in `tests/test_compiler.py`).

## Structure
compiler/ generator/ fuzzer/ ai/ web/ tests/ reports/ main.py
