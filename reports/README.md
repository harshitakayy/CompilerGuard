# reports/

* `runs/<run-id>/` - one folder per pipeline or evaluation run (git-ignored). Run ids look like
  `20261019T094943Z-pipeline-seed42`. A run never overwrites an earlier one.
* `legacy/` - results from the original prototype, kept unchanged for the record. Their format
  differs from the current schema (see `legacy/README.md`).

Files inside a run folder (all UTF-8 JSON with a top-level `schema_version`):

| File | Written by | Content |
|---|---|---|
| `valid_results.json` | pipeline | grammar-generated programs and their results |
| `invalid_results.json` | pipeline | mutation tests (syntax/lexical/semantic) and results |
| `ai_results.json` | pipeline | AI-generated tests, or an empty list plus the reason AI was skipped |
| `error_statistics.json` | pipeline | grouped error patterns, outcome counts, candidate bugs |
| `pipeline_summary.json` | pipeline | totals for the run |
| `lab_result.json` | lab / web UI | three-approach experiment: config, design, per-trial arms (summaries and every executed test), aggregate |
| `evaluation_summary.json` | evaluation | design, per-trial metrics, aggregate mean/stdev |
| `evaluation_details.json` | evaluation | every executed test of every arm and trial |
| `experiment_metadata.json` | both | seed, config, AI availability/model/rounds, timestamps, environment |

Each result record contains: `id`, `category`, `source`, `code`, `expected_status`,
`expected_basis`, `actual_status`, `compiler_response`, `oracle`, `outcome`, `adjudication`,
`potential_compiler_bug`, `bug_reasons`, `error_pattern`, `new_pattern`, `duplicate_of`, `provenance`.
