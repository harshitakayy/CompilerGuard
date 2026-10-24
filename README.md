# CompilerGuard

**An AI-guided compiler testing laboratory.** Pick a language (the course language CG-Lang, a C++ subset, or *your own grammar*),
and CompilerGuard will derive valid programs from its production rules, break them with 22 grammar-aware mutation operators, judge every result against an
independent oracle, and measure - at an equal test budget - what blind mutation, feedback-steered mutation and AI-guided generation actually find.

Everything is available from a luxury-styled web interface (`python server.py`) and from the command line.

> **Honest status.** Everything below that says *measured* was produced by real runs in this repository (250 offline tests pass).
> The AI-guided approach is implemented and tested against a scripted fake service; **it has not been run against the live OpenAI API here**,
> so no AI results are claimed. The C++ target is a substantial **subset** of C++, not the full ISO grammar (see [Limitations](#limitations)).

---

## 1. Quick start (Windows PowerShell)

```powershell
git clone https://github.com/harshitakayy/CompilerGuard.git
cd CompilerGuard
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1            # if blocked: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
python -m pip install -r requirements.txt

python server.py --open                  # web app at http://127.0.0.1:8000
python -m pytest                         # 250 offline tests, no key or network needed
```

The server uses only the Python standard library, binds to `127.0.0.1` by default, and serves both the API and the web UI.

**AI access (optional).** Either set a key for the server (`$env:OPENAI_API_KEY = "..."`, or copy `.env.example` to `.env`), or paste it into the web form for one run.
A key pasted in the browser goes only to *your own* local server for that request; it is never stored, logged, echoed or written to reports.
Do not expose the server to a network if you use that option. Without any key the AI approach is reported as **not run**. The default model is
`gpt-5.4-mini` (carried over from the prototype and not verified here); override with `$env:CG_OPENAI_MODEL`.

## 2. The web interface

| Section | What you do | Backend endpoint |
|---|---|---|
| **I. Choose a language** | CG-Lang, C++ subset, Calculator, JSON-like, an ordered-choice hazard demo, or *your own grammar* | `GET /api/presets` |
| **II. The grammar** | Read the production rules (highlighted) or write your own in EBNF; see rule/production/terminal counts, warnings (left recursion, unreachable rules, ordered-choice hazards) and line-numbered errors | `POST /api/grammar/analyze` |
| **III. Compile a program** | Type a program; see verdict with line/column caret, oracle agreement, tokens, parse tree and the productions used. **The rules it exercises are highlighted in the panel beside the input** | `POST /api/compile` |
| **IV. Generate and mutate** | Generate valid programs or smart mutants; each row shows operator, intent, expected vs actual result and any bug signal; click a row to load it | `POST /api/generate` |
| **V. The experiment** | Choose budget, shared seed tests, batch, trials, seed and whether to include AI; watch live progress; read the dashboard | `POST /api/experiment`, `GET /api/jobs/<id>` |

The production rules are shown next to every input space (compile and experiment), as requested.

### Dashboard metrics (all measured per approach, shown as mean ± sample standard deviation over trials)

| Metric | Definition |
|---|---|
| Unique error patterns | distinct *error type + message* after abstracting names/characters (`Variable '<ID>' is undefined`) |
| Potential bug signals | compiler result disagrees with the independent oracle (status, error type or location). A candidate to investigate, never a proven bug |
| Grammar production coverage | % of BNF productions completed in the Earley chart. Counted even for rejected programs (the part parsed before the error) |
| AST diversity | unique depth-4 parse-tree shapes and unique parent-child production edges, over accepted programs |
| Compiler path coverage | executed / executable lines of the instrumented compiler modules via `sys.settrace` (reported as unavailable if tracing cannot run) |
| New patterns per test | unique patterns / tests, plus a per-test novelty strip (new pattern, new productions or AST shape, new compiler lines) and cumulative discovery curves |

## 3. Languages and grammar notation

| Target | Compiler under test | Oracle |
|---|---|---|
| **CG-Lang** | the hand-written lexer, parser and semantic analyser (`compiler/`) | independent reference recogniser (`harness/oracle.py`) |
| **C++ subset, Calculator, JSON, Hazard** | parser *generated from the grammar* (packrat/PEG, `grammarkit/rdparser.py`) | Earley parser (`grammarkit/earley.py`), which accepts exactly the grammar's language |
| **Your grammar** | same generated parser | same Earley oracle |

**C++ subset** (`grammars/cpp_subset.gr`: 42 rules, 187 productions after desugaring): namespaces and `using`, classes/structs with access
specifiers, functions with parameters, declarations with pointers/references/arrays/initialisers, `if/else`, `switch`, `while`, `do-while`, `for`,
`return/break/continue`, and the complete expression-precedence ladder from the comma operator down to postfix `.`, `->`, `[]`, calls, `++/--`. The lexer skips
comments and `#include` lines. **Not included:** templates, user-defined types as declaration types, casts, lambdas, `new/delete`, overloading, and any semantic analysis.
Real C++ cannot be captured by a context-free grammar alone (it needs symbol tables to parse), so this is deliberately a syntactic subset.

**Your own grammar** - one rule per line (continuations start with `|`):

```text
program    -> statement*                 # first rule is the start symbol
statement  -> ID '=' expression ';'
expression -> term (('+' | '-') term)*   # 'literals', ( groups ), * + ? repetition, | choice
factor     -> NUMBER | ID | '(' expression ')'
```

Built-in token classes: `ID`, `NUMBER`, `STRING`, `CHAR`; `eps` is the empty string; `::=` and `→` also work as arrows; `%number int` makes `NUMBER` digits-only;
`%comments c` skips C-style comments and `#` lines. Analysis reports undefined or non-productive rules with line numbers, and warns about left recursion
(the generated PEG parser cannot handle it and will reject valid input - the oracle will say so), unreachable rules and ordered-choice hazards.
Try the **Ordered-choice hazard** preset to watch the framework raise bug signals.

## 4. How the testing works

1. **Valid programs** - coverage-directed derivation from the productions (seeded, bounded depth, unique). For CG-Lang the semantic-aware generator keeps variables defined.
2. **Smart mutation** (`grammarkit/mutate.py`) - 22 operators in four families. *Token level:* delete, duplicate, swap, replace (same or other class), insert, truncate, drop or add a bracket,
   keyword-as-identifier. *Lexical:* invalid and non-ASCII characters, unterminated literals, number edge cases, fresh (undefined) identifiers.
   *Grammar level* (uses the Earley parse tree and chart): delete a required child, swap or duplicate siblings, splice a subtree from a different rule, truncate at a production
   boundary, regenerate a subtree (a validity-preserving mutation that diversifies AST shapes), and **insert a token the grammar does not expect at that position**.
   The expected status of every mutant is the oracle's verdict; the operator's *intent* is recorded so unrealised intents are visible. The original 30-operator CG-Lang mutation engine remains in `generator/`.
3. **Three approaches, equal budget** (`lab/experiment.py`), sharing the same first *N* tests (paired design):
   *blind* (round-robin operators), *feedback* (operator choice adapts to compiler feedback: new patterns, productions, AST shapes, compiler lines and bug signals; 30% exploration; **needs no API key**),
   and *AI-guided* (an LLM receives the grammar, grouped error patterns, concrete failing examples and the executed programs, and returns validated new programs each round).
   Incomplete or unavailable arms are labelled and excluded from comparisons; nothing is imputed.
4. **Judging** - every program is run through the compiler and the oracle. Compiler = expected: correct. Compiler != expected but = oracle: the expectation was wrong (e.g. an equivalent mutant), *not* a bug.
   Compiler != oracle: **potential bug signal**.

## 5. Results (measured here)

*Test suite:* 250 passed. *Differential check:* the generated PEG parser and the Earley oracle never disagreed on the Calculator, JSON and C++ grammars over 3 seeds x (15 valid programs + 60 mutants each); on the hazard grammar they do, as designed.

*Feedback vs blind mutation, budget 60, 20 shared tests, 5 fresh seeds (100-104), mean ± sd of unique error patterns:*

| Grammar | Blind | Feedback | Feedback ahead in |
|---|---|---|---|
| CG-Lang | 21.2 ± 1.9 | 19.6 ± 2.4 | 1 of 5 trials |
| C++ subset | 41.8 ± 3.2 | 43.4 ± 4.3 | 3 of 5 (1 tie) |
| Calculator | 13.0 ± 0.0 | 12.2 ± 1.3 | 1 of 5 (1 tie) |
| JSON-like | 26.0 ± 1.9 | 28.4 ± 2.3 | 5 of 5 |

**Reading this honestly:** cheap adaptive feedback is *not* consistently better than a strong round-robin baseline. It helps on JSON, is mixed on C++, and trails on the two smallest pattern spaces,
where blind scheduling already saturates. Production coverage and AST/edge diversity are similar or slightly higher for feedback on C++ (e.g. production coverage 77.5 ± 7.0 vs 70.6 ± 8.4 over seeds 42-44).
The exploration rate was fixed in advance, not tuned on these seeds. Whether *AI* feedback adds value is **unmeasured** until you run it with a key:
`python -m lab --target cpp --trials 5 --ai`.

Historical prototype numbers (random 7 vs AI-guided 10 patterns) are author-reported and unverified; they live in `reports/legacy/` and are not comparable to the current definitions.

## 6. Command line

```powershell
python -m lab --target cpp --trials 3                      # three-approach experiment (add --ai with a key)
python -m lab --grammar mine.gr --trials 1 --budget 30     # your own grammar file
python tests\test_runner.py --seed 42                      # original CG-Lang pipeline: 30 valid + 100 mutants (+ AI rounds)
python tests\evaluation.py --trials 5                      # original paired CG-Lang evaluation (budget 60)
python -m compiler -c "x = (10 + 5;" --tokens --ast        # the hand-written CG-Lang compiler
```

Every run writes to a new folder `reports/runs/<timestamp>-<kind>-seed<seed>/` (created automatically, independent of the working directory, never overwritten).
The web experiment saves `lab_result.json` and `experiment_metadata.json` there. Schemas: `reports/README.md`.

### Real output (AI skipped: no key; Python 3.12; produced by actual runs)

```text
$ python -m lab --target cpp --trials 3
Metric                            Mutation (blind)    Mutation + compiler feedback
unique error patterns             40.67 ± 3.51        40.33 ± 2.52
bug signals                       0.00 ± 0.00         0.00 ± 0.00
production coverage pct           70.60 ± 8.39        77.53 ± 7.01
ast unique shapes                 10.33 ± 2.52        10.00 ± 2.65
ast unique edges                  82.33 ± 19.50       91.33 ± 11.68
path coverage pct                 33.00 ± 0.00        33.00 ± 0.00
AI-guided: NOT RUN — AI disabled

$ python tests\test_runner.py --seed 42
Valid programs accepted : 30/30      Mutants rejected : 100/100 (all 30 operators used)
AI tests executed       : 0 (AI status: SKIPPED)    Unique error patterns: 29    Potential compiler bugs: 0 (candidates only)
```

## 7. HTTP API

`GET /api/health` · `GET /api/presets` · `POST /api/grammar/analyze {grammar}` · `POST /api/compile {target|grammar, source}` · `POST /api/generate {target|grammar, kind, count, seed}` ·
`POST /api/experiment {target|grammar, budget, seed_tests, batch, trials, seed, ai:{enabled, api_key}}` -> `{job_id}` · `GET /api/jobs/<id>`.
Inputs are size-limited and clamped (budget 20-200, trials 1-5, two concurrent jobs); static files cannot escape `web/`.

## 8. Limitations

* The C++ target is a syntax-only subset; CG-Lang is the only target with semantic checks.
* For grammar targets the lexer is shared between compiler and oracle, so the differential test covers parsing, not tokenisation.
* The oracle encodes our reading of each grammar; a bug signal can be an oracle bug. Signals need manual investigation.
* The generated parser is PEG-style, so left recursion and some ambiguities produce signals by design; the analysis warns about them.
* "Unique error patterns", coverage and AST diversity describe *diversity of behaviour*, not guaranteed defect-finding power. Path coverage is line-level and `sys.settrace`-based.
* A few trials give descriptive statistics only; no significance tests are claimed. AI output is non-deterministic and model-dependent.
* Tested on Python 3.12 and openai 3.35.1 (written for 3.9+); the browser UI was checked in a headless DOM, not in a visual browser here. The page loads web fonts from Google Fonts and falls back to system serif/sans offline.

## 9. Demonstration sequence (about 10 minutes)

1. `python server.py --open`. Point out the **Backend online** badge.
2. **I-III:** choose *C++ subset*; show the highlighted production rules and counts; compile the sample, open *Parse tree* and *Productions*, note the highlighted rules; click **Break it** and show the caret, expected-token list and oracle agreement.
3. **Custom grammar:** choose *Your own grammar*, edit a rule, show live analysis (try `a -> b` for the line-numbered error and `E -> E '+' T | T` for the left-recursion warning).
4. **Hazard demo:** compile `a b x`: the oracle accepts, the generated parser rejects, a **Bug signal** appears.
5. **IV:** generate smart mutants; discuss operators, intent versus oracle verdict.
6. **V:** run the experiment (budget 60, 3 trials). Walk through the KPI cards, comparison table, discovery curves, novelty strips and coverage-by-rule.
7. Explain the AI banner (not run without a key), then, with a key, rerun with the AI box ticked and show the AI rounds table.

## 10. Project structure

```text
CompilerGuard/
|-- server.py                 backend (API + static web app)
|-- web/                      index.html  style.css  app.js
|-- grammars/                 cglang.gr cpp_subset.gr calc.gr json.gr hazard.gr
|-- grammarkit/               grammar.py lexer.py earley.py rdparser.py generate.py mutate.py
|-- lab/                      targets.py metrics.py experiment.py __main__.py
|-- compiler/                 hand-written CG-Lang front end (lexer, parser, AST, semantic)
|-- generator/                original CG-Lang grammar generator and 30-operator mutation engine
|-- harness/                  oracle.py execution.py analysis.py dedupe.py ai_loop.py pathcov.py reporting.py
|-- ai/                       ai_generator.py (Responses API, JSON schema, validation, secret-safe errors)
|-- tests/                    test_runner.py (pipeline)  evaluation.py  test_*.py (250 tests)  fakes.py
|-- reports/                  runs/ (generated)  legacy/ (original prototype results)
```

Team contributions: *add member names here.* Implemented - compiler front end; grammar engine; generators and mutators; oracle; pipeline, lab and web interface; reports and tests.
Planned - semantic analysis for the C++ target, test minimisation, coverage-guided prioritisation, replay of saved genuine AI responses.
