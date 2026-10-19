# CompilerGuard test report

- Generated: 2026-10-14 06:45:44
- Seed: 1, duration: 0.15s
- Planted faults: none (clean compiler)

## Summary

| Metric | Value |
|---|---|
| Total test programs | 273 |
| Accepted (PASS) / Rejected (FAIL) / Crashed | 53 / 220 / 0 |
| Bugs detected | 0 |
| Unique compiler outcomes (error patterns) | 51 |
| Grammar/semantic rules covered | 32 |

## Verdicts

| Verdict | Count |
|---|---|
| OK | 53 |
| OK_REJECTED | 220 |

## Tests by source

| Kind | Count |
|---|---|
| feedback | 72 |
| mutant | 150 |
| stress | 21 |
| valid | 30 |

## Bugs found

None. Every valid program was accepted with output identical to the reference implementation, and every guaranteed-invalid mutant was rejected.

## Compiler outcomes observed

| Outcome | Count |
|---|---|
| PASS | 53 |
| SYNTAX_ERROR: Expected RPAREN but got SEMICOLON | 15 |
| LEXICAL_ERROR: Illegal character '_' | 14 |
| SEMANTIC_ERROR: Undefined variable '_' | 14 |
| SYNTAX_ERROR: Expected ASSIGN but got NUMBER | 13 |
| LEXICAL_ERROR: Malformed number literal | 11 |
| SYNTAX_ERROR: Expected ASSIGN but got IDENT | 11 |
| SYNTAX_ERROR: Expected expression but got PLUS | 9 |
| SYNTAX_ERROR: Expected expression but got PERCENT | 8 |
| SYNTAX_ERROR: Expected expression but got SEMICOLON | 8 |
| SYNTAX_ERROR: Expected statement but got ASSIGN | 8 |
| SYNTAX_ERROR: Expected SEMICOLON but got RPAREN | 7 |
| SYNTAX_ERROR: Expected expression but got ASSIGN | 7 |
| SYNTAX_ERROR: Expected ASSIGN but got LPAREN | 7 |
| SEMANTIC_ERROR: Division by zero | 6 |
| SYNTAX_ERROR: Expected SEMICOLON but got NUMBER | 6 |
| SYNTAX_ERROR: Expected SEMICOLON but got IDENT | 5 |
| SYNTAX_ERROR: Expected SEMICOLON but got PRINT | 5 |
| SYNTAX_ERROR: Expected expression but got STAR | 5 |
| SYNTAX_ERROR: Expected LBRACE but got RPAREN | 5 |
| SYNTAX_ERROR: Expected comparison operator but got NUMBER | 4 |
| SYNTAX_ERROR: Expected statement but got LPAREN | 3 |
| SYNTAX_ERROR: Expected SEMICOLON but got LPAREN | 3 |
| SYNTAX_ERROR: Expected ASSIGN but got MINUS | 3 |
| SYNTAX_ERROR: Expected statement but got LBRACE | 3 |
| SYNTAX_ERROR: Expected RPAREN but got LBRACE | 3 |
| LEXICAL_ERROR: Number literal too large | 3 |
| LIMIT_ERROR: Nesting too deep (limit 100) | 3 |
| SYNTAX_ERROR: Expected comparison operator but got RPAREN | 2 |
| SYNTAX_ERROR: Expected statement but got SEMICOLON | 2 |
| SYNTAX_ERROR: Expected LPAREN but got IDENT | 2 |
| SYNTAX_ERROR: Expected RPAREN but got NUMBER | 2 |
| SYNTAX_ERROR: Expected LBRACE but got IF | 2 |
| SYNTAX_ERROR: Expected RBRACE but got EOF | 2 |
| RUNTIME_ERROR: Division by zero | 2 |
| SYNTAX_ERROR: Expected comparison operator but got IDENT | 2 |
| SYNTAX_ERROR: Expected comparison operator but got LPAREN | 1 |
| SYNTAX_ERROR: Expected LBRACE but got PRINT | 1 |
| SYNTAX_ERROR: Expected SEMICOLON but got EOF | 1 |
| SYNTAX_ERROR: Expected RPAREN but got LT | 1 |
| SYNTAX_ERROR: Expected ASSIGN but got RBRACE | 1 |
| SYNTAX_ERROR: Expected expression but got LT | 1 |
| SYNTAX_ERROR: Expected SEMICOLON but got RBRACE | 1 |
| SYNTAX_ERROR: Expected expression but got PRINT | 1 |
| LIMIT_ERROR: Expression too deeply nested | 1 |
| RUNTIME_ERROR: Numeric overflow (value too large) | 1 |
| RUNTIME_ERROR: Execution step limit exceeded (possible infinite loop) | 1 |
| SYNTAX_ERROR: Expected statement but got RBRACE | 1 |
| SYNTAX_ERROR: Expected SEMICOLON but got WHILE | 1 |
| SYNTAX_ERROR: Expected SEMICOLON but got IF | 1 |
| SYNTAX_ERROR: Expected expression but got SLASH | 1 |
