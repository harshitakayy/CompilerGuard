# Legacy prototype reports

Files here were produced by the original prototype runner and are kept as-is (moved, not edited).
They use the old format (a bare list of `{code, expected, actual, result, passed}`).

Observations when re-reading them:

* `ai_results.json` contains 5 AI tests; test #1 (`b = a / (a - a);`) was **accepted** by the compiler,
  while the old README stated that all five AI tests were rejected with `SYNTAX_ERROR`. CG-Lang does not
  evaluate expressions, so division by zero is not a compile-time error - the old expectation of `FAIL`
  was wrong, not the compiler.
* `prototype_reported_results.json` holds the 45-test comparison numbers reported by the author. Its raw data
  is not in the repository, so it is labelled `historical_reported_unverified`.
