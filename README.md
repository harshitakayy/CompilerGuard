# CompilerGuard

AI-guided grammar-based compiler fuzzing with feedback-driven test generation.
Mini project for BCSE307P Compiler Design Lab, VIT Vellore.

Team: Ocean Verma (24BCT0169), Harshita Kumawat (24BKT0141), Keerthana B (24BCT0314)
Guide: Prof. Muthunagai S U

## What it does

CompilerGuard tests a small compiler automatically. It builds valid programs from the
grammar of the language, breaks them in controlled ways, runs every program through the
compiler and checks whether the compiler behaved correctly. The errors the compiler
reports are collected and used to decide what to test next.

The language under test is CG-Lang, a tiny language with assignments and arithmetic:

```
x = 10 + 5;
y = x * 2;
z = (7 + 2) * 3;
```

Grammar:

```
program    -> statement*
statement  -> ID '=' expression ';'
expression -> term (('+' | '-') term)*
term       -> factor (('*' | '/') factor)*
factor     -> NUMBER | ID | '(' expression ')'
```

A variable can only be used after an earlier statement has assigned it.

## How it works

1. **Generate** valid programs from the grammar (seeded, so runs can be repeated).
2. **Mutate** them with 30 operators: syntax breaks (missing semicolon, unbalanced
   brackets, operator in the wrong place), lexical breaks (invalid characters, decimals,
   non-ASCII) and semantic breaks (undefined variables, use before definition).
3. **Run** every program through the compiler (lexer, parser, semantic analysis).
4. **Check** the result against the expected one and against an independent reference
   checker (the oracle). If the compiler and the oracle disagree, it is reported as a
   possible bug.
5. **Analyse** the error messages, group them into patterns and use them to steer the
   next batch of tests.

The same idea is also available for other grammars (a C++ subset, a calculator, a
JSON-like language, or one you type in) through the web page.

## Setup

Windows PowerShell:

```powershell
git clone https://github.com/harshitakayy/CompilerGuard.git
cd CompilerGuard
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If PowerShell blocks the activate script:
`Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`

## Running

Web interface:

```powershell
python server.py --open
```

It opens at http://127.0.0.1:8000. You can pick a language, compile a program and see the
tokens, parse tree and error position, generate valid programs and mutants, and run an
experiment that compares the testing approaches.

Command line:

```powershell
python tests\test_runner.py --seed 42            # generate, mutate, run, analyse
python tests\evaluation.py --trials 5            # compare approaches at equal test budget
python -m lab --target cglang --trials 3         # same comparison through the lab module
python -m compiler -c "x = (10 + 5;" --tokens    # use the compiler directly
python -m pytest                                 # run all tests
```

Every run saves its results in a new folder under `reports/runs/`.

## Sample output

`python tests\test_runner.py --seed 42`

```
Valid programs accepted : 30/30
Mutants rejected        : 100/100
Unique error patterns   : 29
Potential compiler bugs : 0
```

Compiling a broken program:

```
> python -m compiler -c "x = 10 + 5"
{
  "status": "FAIL",
  "type": "SYNTAX_ERROR",
  "line": 1,
  "column": 11,
  "message": "Expected SEMICOLON but got EOF"
}
```

## Optional: OpenAI key

The AI-guided mode sends the grammar and the collected error patterns to an OpenAI model
and asks for new test programs. It needs an API key. Copy `.env.example` to `.env` and put
the key in it, or set `OPENAI_API_KEY` in the terminal. The key is not saved anywhere and
`.env` is ignored by git. Everything else works without it.

## Folder structure

```
server.py        web server (API + web page)
web/             index.html, style.css, app.js
compiler/        lexer, parser, AST, semantic analysis for CG-Lang
generator/       grammar-based program generator and mutation operators
harness/         oracle, test execution, error analysis, duplicate handling, reports
grammarkit/      grammar reader, Earley parser, generated parser, mutators for other grammars
grammars/        .gr grammar files
lab/             experiment runner and metrics
ai/              AI test generator
tests/           pytest tests and the pipeline scripts
reports/         results of runs
```

## Limitations

- CG-Lang is small: only assignments and arithmetic, no loops, conditions or functions.
- The C++ grammar is a subset and only checks syntax.
- A disagreement between the compiler and the oracle needs to be checked by hand. It can
  be a bug in either one.