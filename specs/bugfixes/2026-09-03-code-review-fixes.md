# Bugfix Specification: Code Review and Hardening Pass

**Date:** 2026-09-03  
**Slug:** `code-review-fixes`  
**Status:** Implemented — full regression suite passes (130 tests)
**Initial baseline:** 84 tests passed before the first repair pass; the first
pass reached 113 tests. The follow-up repairs and focused regression coverage
raised the suite to 130 passing tests.

## Objective

Correct the verified defects in the existing static-analysis, project-run,
reporting, and plugin foundations before adding dynamic HTTP assessment or
other new product capabilities.

This specification records the completed repair milestone and its regression
gate. Future changes must preserve the corrected behavior described here.

## Priority and implementation boundary

Complete the P1 correctness and provenance fixes first. The original priority
headings below classify findings 1–14. The explicit follow-up priority map is:

- **Follow-up P1:** findings 15, 16, 17, 19, 21, 22, and 23;
- **Follow-up P2:** findings 18 and 20.

P2 fixes may follow in the same hardening branch, but new dynamic-assessment
feature work must not begin until both the original P1 items and all follow-up
P1 items pass their regression tests.

The changes must preserve existing standalone behavior for `run`, `scan`,
`eval`, and `replay`, except where this specification explicitly corrects
incorrect output placement, ordering, parsing, or telemetry.

## Original P1 — correctness and provenance (findings 1–7)

### 1. Project-scoped generic-run outputs escape the run directory

**Confirmed behavior:** `vharness run --project PATH --evaluators json` writes
the default `report.json` into the process working directory. Selecting the
metrics evaluator similarly writes `eval_metrics.json` outside the project run.

**Required fix:** For every project-scoped generic `run`, assign project-local
defaults before evaluator execution:

```text
out         = <run>/reports/report
metrics_out = <run>/reports/eval_metrics.json
log_file    = <run>/events.jsonl
```

SARIF, Markdown, and JSON derive their filenames from `out`; metrics uses
`metrics_out`. Explicit user-provided output paths remain untouched. Record
structured output provenance for them as specified in finding 22, including
whether each resolves to `explicit_project` or `explicit_external`.

**Regression tests:** Exercise generic project runs with each file-writing
evaluator and assert that no default report appears in the working directory.
Also verify that explicit project-local and external paths remain supported
and receive the correct ownership classification.

### 2. Project launch inputs omit effective workflow configuration

**Confirmed behavior:** Project `run.json` does not record `probes`,
`evaluators`, `detectors`, or `skip_corpus`. Merely adding raw argparse fields
would still omit effective defaults and could record values different from
those used by the runner.

**Required fix:** Introduce one normalization path used by both execution and
project metadata. Persist normalized effective values after preset and default
resolution, for example:

```json
{
  "probes": ["corpus"],
  "detectors": ["json-verdict"],
  "evaluators": ["summary"],
  "skip_corpus": false
}
```

Continue excluding API keys and other secrets. Preserve the existing contract
that `run.json` contains immutable launch inputs and non-secret provenance.

**Regression tests:** Cover generic `run`, `scan`, and `eval`, including
defaults, comma-separated selections, presets, and `--skip-corpus`.

### 3. Explicit `--detectors` values are iterated as characters

**Confirmed behavior:** Argparse produces the string `"json-verdict"`, while
`Runner` expects a list. The runner therefore attempts to load detectors named
`"j"`, `"s"`, `"o"`, and so on.

**Required fix:** Add a shared name-list normalizer that accepts either a
comma-separated string or a sequence, trims whitespace, removes empty entries,
and supplies an explicit default. Use the normalized list for validation,
execution, logs, and project metadata. Apply the same normalization discipline
to probes and evaluators so the contracts cannot drift.

**Regression tests:** Cover one detector, multiple comma-separated detectors,
a programmatic list, whitespace, empty elements, unknown names, and the default.

### 4. SARIF construction can emit invalid rule indices

**Confirmed behavior:** Rule indices are calculated while the rule dictionary
is still being built. When a later finding inserts a lexically earlier CWE,
previous results retain an index that no longer identifies their rule in the
final sorted rule array.

**Required fix:** Build the complete rule set before constructing results.
Create one stable sorted rule list and a `rule_id -> index` map, then use that
map for every result.

When multiple findings share one CWE but carry different severities, define the
rule-level `security-severity` deterministically as the highest normalized
severity. Result properties retain each finding's original severity.

**Regression tests:** Include reverse-sorted CWEs, repeated CWEs, and mixed
severity findings; assert every result's `ruleIndex` points to its `ruleId`.

### 5. SARIF crashes on an unexpected severity

**Confirmed behavior:** The direct severity dictionary lookup raises
`KeyError` for findings emitted by a plugin or caller with an unexpected
severity string.

**Required fix:** Centralize severity normalization/fallback. Unknown values
must not crash report generation. Use the documented Medium-equivalent SARIF
security severity (`"5.0"`) as the fallback, consistent with the existing
warning-level behavior, and retain the supplied value in result properties for
diagnostics.

This fix must be implemented together with the rule precomputation in item 4;
changing only the dictionary lookup is incomplete.

**Regression tests:** Cover `High`, `Medium`, `Low`, an unknown string, and one
CWE represented by mixed known and unknown severities.

### 6. A vulnerable verdict can contain no valid findings

**Confirmed behavior:** If `has_vulnerability` is true but every vulnerability
entry fails validation, the detector leaves the attempt as `status="ok"` and
`verdict="vulnerable"` with an empty finding list. Metrics count this as a
positive prediction while reports contain no corresponding evidence-bearing
finding.

**Required invariant:**

```text
status == "ok" and verdict == "vulnerable"
    implies len(findings) > 0
```

If the model asserts a vulnerability but supplies no usable finding, record a
parse/validation error with diagnostic notes. Do not silently count it as a
validated vulnerable prediction. A future hypothesis state may represent
unvalidated claims, but that state is outside this repair.

**Regression tests:** Cover an empty list with `has_vulnerability=true`, a list
whose entries are all invalid, a mixed valid/invalid list, and a valid clean
response.

### 7. Plugin entry-point loading is not idempotent or fully contained

**Confirmed behavior:** `load_entry_points()` claims to be idempotent, but each
`Runner` loads and registers the same entry points again. A second runner can
fail with a duplicate-name error. Exceptions raised by `register_plugins()` or
`registry.register()` also escape the existing `ep.load()` exception handler.

**Required fix:** Track entry-point identities that were successfully handled,
skip them on subsequent loads, and contain failures from loading and
registration with useful diagnostics. Do not mark a failed entry point as
successfully loaded unless retry behavior is deliberately specified and tested.
Duplicate component names must produce a clear diagnostic naming both the
entry point and registry rather than an unrelated runner failure.

**Regression tests:** Construct two runners against the same fake entry point;
cover class registration, `register_plugins()`, import failure, activation
failure, and duplicate-name diagnostics.

## Original P2 — robustness, determinism, and telemetry (findings 8–14)

### 8. Integer CWE values are discarded

**Confirmed behavior:** A model response containing `{"cwe": 78}` loses the
finding because `_normalize_cwe` accepts strings only.

**Required fix:** Accept positive integer CWE identifiers in the supported
range and normalize them to `CWE-<number>`. Explicitly reject booleans and
floats; do not rely on Python's `bool` subclassing `int` or stringify arbitrary
objects. Preserve the existing compatible handling of descriptive string CWE
values unless stricter parsing is specified separately.

**Regression tests:** Cover an integer, numeric string, canonical string,
descriptive string, zero/negative/out-of-range integer, boolean, float, null,
and unrelated text.

### 9. Null optional finding fields become the string `"None"`

**Confirmed behavior:** JSON `null` values for `sink` and `patch` are converted
through `str()` and persisted as the literal text `"None"`.

**Required fix:** Normalize optional text fields with a helper that returns a
trimmed string only for actual strings and returns `""` for null or unsupported
types. Do not stringify lists, mappings, or numeric values into reports.

**Regression tests:** Cover missing, null, empty, numeric, list, mapping, and
normal string values for both fields.

### 10. Report evaluators do not create parent directories

**Confirmed behavior:** Explicit nested output paths fail with
`FileNotFoundError` when their parent directory does not already exist.

**Required fix:** Use one output helper to create parent directories before
writing SARIF, Markdown, JSON, and metrics reports. Apply the same behavior to
the standalone `write_sarif()` API. Runner log paths already create their
parents and must retain that behavior.

Atomic report replacement is desirable future hardening but is not required to
close this defect.

**Regression tests:** Exercise nested relative and absolute paths for every
writer and verify existing files are replaced as currently documented.

### 11. File-routing callers truncate headers below analyzer requirements

**Confirmed behavior:** Distro configuration analyzers inspect as many as 4,000
header bytes, but routing callers provide only 256. Valid `.service`, `.hook`,
udev, or sudoers-style files with long comment headers can therefore be missed.

**Required fix:** Define one shared constant such as
`ROUTING_HEADER_BYTES = 4096` and use it in all routing paths:

- `FileProbe.attempts()`;
- `FileProbe.route()`; and
- `route_file()`.

Do not update only one literal. Keep full-file size and model prompt limits
separate from this routing-header limit.

**Regression tests:** Place identifying markers around bytes 300, 2,000, and
3,900 and exercise both direct probe matching and multi-probe routing.

### 12. Multi-worker runs return attempts in completion order

**Confirmed behavior:** `as_completed()` causes the returned attempt list,
reports, and per-sample metrics to depend on model latency rather than stable
probe discovery order.

**Required fix:** Retain completion-order progress reporting, but associate
each future with its original attempt index and return results in discovery
order. Add `attempt_index` to JSONL attempt records so completion-ordered logs
remain immediately durable while consumers can reconstruct discovery order.

Do not sort by random attempt ID or by source after completion; preserve the
exact original sequence produced by the probes.

**Regression tests:** Use a delayed fake generator that completes attempts in
reverse order. Assert completion progress remains usable, returned attempts
follow discovery order, reports/metrics are deterministic, and logged indices
are complete and unique.

### 13. Generator summary is captured before execution

**Confirmed behavior:** CLI code builds `generator_summary` before
`runner.run()`. Because the generator is lazy at that point, the summary is
always empty and the Summary evaluator omits query, token, and latency data.

**Required fix:** Capture the summary after a real run and before evaluator
execution. Add an explicit lazy-generator API such as
`summary_if_initialized()` so dry runs do not instantiate clients merely to
produce telemetry.

**Regression tests:** Verify real runs print populated telemetry, cached runs
report cache hits, error runs report API errors, and dry runs do not construct
the generator.

### 14. Generator telemetry updates are not thread-safe

**Confirmed behavior:** `cache_hits`, `queries`, and `api_errors` are mutated
outside the existing lock while a shared generator is used by multiple worker
threads.

**Required fix:** Add a dedicated statistics lock. Protect every statistics
mutation and take a complete snapshot, including a copy of the latency list,
under that lock in `summary()`. Keep cache/database synchronization separate so
telemetry reads do not unnecessarily share the SQLite critical section.

This repair does not need to coalesce concurrent identical cache misses; that
is a separate optimization.

**Regression tests:** Use a deterministic fake client with concurrent success,
cache-hit, retry, and terminal-error paths. Assert exact counters rather than
testing timing.

## Required regression-test gate

Before implementation is considered complete, the suite must cover:

- project-local generic JSON, SARIF, Markdown, and metrics defaults;
- explicit external output compatibility;
- normalized effective project launch inputs;
- string/list detector selection and validation;
- valid-finding/verdict invariants;
- integer and malformed CWE values;
- null and non-string optional finding fields;
- stable SARIF rule indices and unknown/mixed severity handling;
- nested output directory creation;
- 4 KiB routing headers through every routing entry point;
- deterministic returned attempt order and logged `attempt_index` values;
- post-run and dry-run generator summary behavior;
- exact concurrent telemetry totals; and
- repeated runner construction with successful and failing entry points.

Run the complete existing test suite after the focused regression tests. No
existing SAST, replay, project, metrics, or standalone-output behavior may
regress except where this document explicitly changes incorrect behavior.

## Historical implementation order (superseded)

This was the first-pass order for findings 1–14. The revised implementation
order at the end of this document is authoritative and supersedes this section.

1. Add failing regression tests for P1 items 1–7.
2. Implement normalized CLI/workflow inputs and project output routing.
3. Repair detector validity and SARIF construction.
4. Make plugin discovery idempotent and failure-contained.
5. Add failing regression tests for P2 items 8–14.
6. Implement parser, writer, routing, ordering, and telemetry repairs.
7. Run the focused tests, concurrency tests, and complete suite.
8. Update this document to `Implemented` only after the fixes and tests land.

## Completion criteria

This hardening milestone is complete when:

- all 23 documented defects and all listed regression gaps have focused
  coverage;
- the complete test suite passes;
- project-scoped runs leave no unrequested default outputs in the working
  directory;
- reports and metrics are deterministic and evidence-bearing;
- repeated Runner construction cannot duplicate plugin registration; and
- generator telemetry remains exact under configured worker concurrency.

## Follow-up review findings

The first implementation pass reached 113 passing tests; a second read-only
review found the defects below. They are resolved by the implementation and
regression coverage recorded in this milestone.

Follow-up priorities are:

- **P1:** findings 15, 16, 17, 19, 21, 22, and 23;
- **P2:** findings 18 and 20.

### 15. Plugin activation can leave partial registration behind

**Confirmed behavior:** `load_entry_points()` does not mark a failing entry
point as loaded, which permits a later retry. However, `register_plugins()` may
successfully register one or more components before raising. Those registry
mutations remain. A later retry can then fail with duplicate component names,
leaving plugin availability dependent on the point of failure.

**Required fix:** Make plugin activation transactional and synchronize the
complete activation operation. Use one re-entrant shared lock covering the
loaded-identity check, entry-point import/activation, every registry mutation,
instance-cache mutation, rollback, and loaded-identity commit. The lock must be
re-entrant because decorator-triggered registration can occur during
`ep.load()`. Concurrent Runner construction and direct registry mutation must
not race with activation or rollback. A preferred implementation stages
registrations and commits them only after activation succeeds. If staging is
not feasible with the current decorator API, snapshot both registered items
and cached instances before `ep.load()` and restore them on failure while the
same lock remains held. Preserve useful diagnostics naming the entry point and
affected registry/component. Add the loaded identity only after the
registration transaction commits.

**Regression tests:** Cover an import failure, a `register_plugins()` failure
before registration, a failure after one successful registration, a retry of
each failure, class registration, duplicate-name diagnostics, and concurrent
activation from multiple Runner constructions. Assert that failed activation
leaves no new components or cached instances behind and successful activation
occurs exactly once.

### 16. Unexpected worker-future failures can return pending attempts

**Confirmed behavior:** The completion loop falls back to the original
attempt object when a worker future raises outside the normal generator or
detector handler. That attempt may retain `status="pending"`. The run can then
omit it from all terminal counters while describing the run as complete.

**Required fix:** Every discovered attempt must reach exactly one terminal
status. If a future raises, mark its original attempt `internal_error`, set an
error verdict and diagnostic note, record its `attempt_index`, and include it
in run counters and the durable `run_end` record. If durable attempt logging
itself fails, surface a run-level failure rather than claiming a fully recorded
successful run.

**Regression tests:** Force an exception outside the inner work handler and
assert stable returned order, no pending attempts, exact internal-error counts,
complete unique indices, and appropriate run-level behavior when JSONL writing
fails.

### 17. String CWE parsing bypasses integer range validation

**Confirmed behavior:** Integer CWE values are bounded, but strings are parsed
with a substring regex. Values such as `"10000"`, `"0"`, and `"-1"` may be
truncated or normalized into an invalid CWE. Unrelated text containing a short
number may also be accepted.

**Required fix:** Parse canonical, numeric, and supported descriptive string
forms without truncation, then apply the same supported range of `1..9999`
used for integers. Numeric strings must be validated as complete numeric
tokens. Descriptive compatibility must require an explicit CWE marker rather
than an arbitrary number appearing in prose.

**Regression tests:** Add string forms for zero, negative, five-or-more digit,
leading/trailing text, unrelated numbered prose, canonical values, numeric
values, and supported descriptive `CWE <id> description` values.

### 18. Plugin listing does not discover installed entry points

**Confirmed behavior:** `vharness list` prints the current registries without
calling `load_entry_points()`. Installed third-party plugins therefore remain
absent until another code path constructs a runner or otherwise loads entry
points.

**Required fix:** Perform contained, idempotent entry-point discovery before
listing registries. A broken plugin must produce a diagnostic without hiding
built-ins or preventing other plugins from appearing.

**Regression tests:** Invoke `list` in a fresh process state with successful
and failing fake entry points. Assert built-ins and successful third-party
components appear exactly once and failures are diagnosed.

### 19. Retried generations under-report locally recorded token usage

**Confirmed behavior:** Generator statistics include tokens from a
length-truncated response and its successful retry, but the returned
`Generation` contains only the final response's tokens. Attempt JSONL records
and `vharness usage` therefore undercount locally observed billable usage.

**Required fix:** Accumulate prompt and completion tokens plus cumulative
observed response latency across every response received for one logical
generation and store those totals in the returned `Generation`, including when
a later retry ends in a terminal error. Preserve optional per-response
telemetry when it becomes useful, but the attempt-level totals must represent
all observed provider usage. Update `read_usage()` to count recorded tokens and
latency independently from the logical success/error classification; its
current early `continue` on `generation.error` would otherwise discard the
newly preserved billable usage. Cache hits remain zero-token local responses.

**Regression tests:** Cover immediate success, one and multiple length retries,
terminal error after a billable response, cache hits, and concurrent mixed
paths. Assert generator summary, `Generation`, JSONL, and `vharness usage`
agree on token and cumulative-latency totals.

### 20. Name-list normalization silently drops malformed values

**Confirmed behavior:** Programmatic sequences containing non-string values
silently discard those values. A malformed selection such as
`["json-verdict", 42]` appears valid rather than producing a configuration
error.

**Required fix:** Accept only a comma-separated string or a sequence containing
strings. Trim strings and remove empty entries, but reject unsupported input
types and non-string sequence members with a diagnostic identifying the field
and invalid value. Continue applying explicit defaults only when the normalized
selection is genuinely empty.

**Regression tests:** Cover strings, tuples/lists, whitespace, empty elements,
empty selections, integers, mappings, mixed sequences, unknown names, and
defaults through both CLI and programmatic runner paths.

### 21. Contradictory verdict flags and findings lack a defined policy

**Confirmed behavior:** A response with `has_vulnerability=false` and one or
more valid vulnerability objects becomes `verdict="vulnerable"` because valid
findings take precedence implicitly. The contradiction is not reported.

**Required fix:** Define and document precedence. When
`has_vulnerability=false`, `vulnerabilities` must be absent or exactly an empty
list. Any nonempty list is a parse/validation error, including a list whose
entries are all malformed, and any non-list value is also a parse/validation
error. Do not silently reinterpret the model's assertion. Preserve the
invariant that an `ok` vulnerable verdict has at least one valid finding.

**Regression tests:** Cover false plus valid findings, false plus invalid
findings, true plus valid findings, true plus none, missing flag plus valid
findings, and a valid clean response.

### 22. Relative external output provenance is ambiguous

**Confirmed behavior:** Project run metadata records an explicit relative
output path exactly as supplied. Once the launch working directory is lost,
`run.json` cannot identify the actual external output location.

**Required fix:** Preserve the user-supplied value for reproducibility while
also recording its absolute path resolved against the launch working
directory. Record the launch working directory once in immutable inputs or
provenance. Canonicalize existing symlink parents before ownership
classification. Store structured output provenance containing at least
`requested`, `resolved`, and `ownership`. Distinguish `project_default`,
`explicit_project`, and `explicit_external`; an explicitly supplied path inside
the project is not automatically external. A lexically project-local path that
resolves outside the project is `explicit_external`, while a lexically external
path that resolves inside the project is `explicit_project`.

**Regression tests:** Cover relative and absolute explicit paths for every
report/log output, a launch working directory outside the project, project
defaults, and metadata reconstruction after changing directories.

### 23. Failed or unparseable attempts corrupt evaluation metrics

**Confirmed behavior:** The confusion matrix scores every labeled attempt
without checking its terminal status. A parse error on a clean sample is counted
as a true negative, while an API or internal error on a vulnerable sample is
counted as a false negative. These are unavailable predictions, not model
security judgments. Stricter detector validation therefore changes precision,
recall, and false-positive rates for the wrong reason.

**Required fix:** Compute TP, FP, TN, FN, clean-sample false-positive rate, CWE
accuracy, and per-CWE recall only from eligible predictions:

```text
status == "ok"
verdict in {"clean", "vulnerable"}
```

Report coverage and unscored outcomes using this complete schema:

```text
labeled_total
scored_total
unscored_parse_error
unscored_api_error
unscored_internal_error
unscored_skipped
unscored_other
coverage = scored_total / labeled_total
```

These counters are disjoint and exhaustive over labeled attempts: every
labeled attempt contributes to exactly one of `scored_total` or the five
`unscored_*` counters. The named error and skipped counters classify their
corresponding terminal statuses. `unscored_other` includes all remaining
unavailable predictions, including unknown or missing statuses and
`status="ok"` with an unsupported verdict. The counts must sum exactly to
`labeled_total` according to this mandatory accounting identity:

```text
labeled_total == scored_total
                 + unscored_parse_error
                 + unscored_api_error
                 + unscored_internal_error
                 + unscored_skipped
                 + unscored_other
```

Define `coverage` as `scored_total / labeled_total`, or `0.0` when
`labeled_total == 0`. Preserve the existing `labeled` field as a compatibility
alias whose value is exactly `labeled_total`. Do not convert
transport, parser, or harness failures into clean predictions or model misses.
`clean_total`, TP/FP/TN/FN, CWE accuracy, and per-CWE denominators must use only
eligible scored predictions. Preserve every labeled sample, its status, and
diagnostic notes in per-sample metrics output.

**Regression tests:** Cover clean and vulnerable samples for every `ok`
verdict, plus parse, API, internal, and skipped statuses. Assert failed attempts
do not enter the confusion matrix or per-CWE denominators, coverage is exact,
empty-set coverage is `0.0`, the disjoint counters sum exactly to
`labeled_total`, `labeled == labeled_total`, and the human and JSON metric
summaries expose the complete schema.

## Follow-up regression coverage delivered

The originally required cases were added or strengthened as follows:

- project-scoped generic runs with JSON, SARIF, Markdown, and metrics tested
  independently;
- explicit external output compatibility for every output type;
- effective `scan` and `eval` metadata, including `--skip-corpus`;
- unknown detector and evaluator validation;
- nested relative and absolute output paths and replacement behavior;
- retry, cache-hit, and terminal-error generator summaries;
- deterministic per-sample metric/report ordering under reversed completion;
- metrics eligibility and coverage for parse/API/internal/skipped attempts;
- concurrent plugin activation and cached-instance rollback; and
- retry token totals flowing through `Generation`, JSONL, and `read_usage()`.

## Completed implementation order

This completed order supersedes the historical first-pass order.

1. Add failing regression tests for findings 15–23 and the remaining gate
   gaps above.
2. Make plugin activation rollback-safe, synchronized, and available to
   `vharness list`.
3. Guarantee terminal attempt state for every worker outcome.
4. Harden CWE parsing, name selection, and contradictory verdict validation.
5. Make attempt-level usage totals include all observed retry responses.
6. Exclude failed/unavailable predictions from security-quality metrics and
   report coverage explicitly.
7. Record unambiguous output provenance.
8. Run focused tests, concurrency tests, and the complete suite.
9. Change this document to `Implemented` after every original and follow-up
   completion criterion passes.
