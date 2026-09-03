# Bugfix Specification: Code Review and Hardening Pass

**Date:** 2026-09-03  
**Slug:** `code-review-fixes`  
**Status:** Approved for implementation  
**Baseline:** 84 tests pass, but the defects below are not covered by the
current suite.

## Objective

Correct the verified defects in the existing static-analysis, project-run,
reporting, and plugin foundations before adding dynamic HTTP assessment or
other new product capabilities.

This specification is a repair milestone, not evidence that the defects have
already been fixed. Implementation is complete only when the regression tests
and completion gate in this document pass.

## Priority and implementation boundary

Complete the P1 correctness and provenance fixes first. P2 fixes may follow in
the same hardening branch, but new dynamic-assessment feature work must not
begin until all P1 items pass their regression tests.

The changes must preserve existing standalone behavior for `run`, `scan`,
`eval`, and `replay`, except where this specification explicitly corrects
incorrect output placement, ordering, parsing, or telemetry.

## P1 — correctness and provenance

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
`metrics_out`. Explicit user-provided output paths remain untouched and are
recorded as external output locations.

**Regression tests:** Exercise generic project runs with each file-writing
evaluator and assert that no default report appears in the working directory.
Also verify that explicit external paths remain supported.

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

## P2 — robustness, determinism, and telemetry

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

## Implementation order

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

- all fourteen defects have focused regression coverage;
- the complete test suite passes;
- project-scoped runs leave no unrequested default outputs in the working
  directory;
- reports and metrics are deterministic and evidence-bearing;
- repeated Runner construction cannot duplicate plugin registration; and
- generator telemetry remains exact under configured worker concurrency.
