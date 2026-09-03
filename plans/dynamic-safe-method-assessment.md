# Dynamic safe-method assessment: Phase 1

## Objective

Add a small, generic dynamic-assessment vertical slice to `vharness` for
locally authorized lab targets. The slice must prove that the assessment loop,
scope boundary, policy feedback, evidence persistence, and CLI are useful
before broader dynamic capabilities are added.

BlackVault is an external acceptance target owned by `~/xtests/blackvault`.
It must not introduce target-specific routes, exploit logic, challenge names,
or flag-handling behavior into `vharness`.

## Authority and boundary

This is the binding dynamic-assessment Phase 1 implementation and acceptance
contract. It follows the prerequisite Workspace v0 contract in
`workspace-project-foundation.md` and overrides broader roadmap language in
`plans.md` for dynamic Phase 1. It has one sequential planner, one
single-origin HTTP capability, a fixed safe-method policy, and no resumable or
multi-agent execution.

Phase 1 constructs and persists an immutable internal scope snapshot from the
CLI target and this fixed policy. User-authored manifests, CIDRs, DNS names,
generalized policy tiers, crawling, and remote authorization are post-Phase-1
capabilities.

## Non-goals

This phase does not:

- capture BlackVault flags or attempt to validate its vulnerabilities;
- supply target source, hints, route lists, or solutions to the planner;
- send `POST`, `PUT`, `PATCH`, or `DELETE` requests;
- support request bodies, authentication, cookies, uploads, arbitrary
  request headers, shell execution, filesystem access, or concurrency;
- support remote targets, DNS names, general crawling, or third-party targets;
- emit SARIF findings, resume sessions, or implement the wider AgentStorm
  architecture.

`GET` and `HEAD` are method-limited requests, not a guarantee that a target
handler is read-only. The CLI and documentation must say this explicitly.

## User-facing command

```bash
vharness assess \
  --project . \
  --target http://127.0.0.1:5050 \
  --mode safe-method \
  --max-decisions 12 \
  --max-requests 16 \
  --max-redirects 3 \
  --max-duration 60 \
  -vv
```

`assess` requires a Workspace v0 project. It stores authoritative SQLite state,
ordered JSONL export, reports, and evidence under the created project's run
directory. A project organizes local state only; its manifest cannot broaden
the literal-loopback scope or safe-method policy.

At startup, print the canonical origin, literal-loopback restriction, allowed
methods, redirect policy, and budgets. For example:

```text
[scope] http://127.0.0.1:5050 — literal loopback origin
[mode] safe-method — GET/HEAD only; target handlers may still change state
[budget] 12 decisions, 16 requests, 3 redirects/request, 60 seconds
```

The final summary must name one of these stop reasons:

```text
model_complete | decision_budget | request_budget | duration | duplicate |
error_threshold | operator_interrupt
```

Normal completion and budget exhaustion exit successfully. Invalid scope or
configuration retains the CLI's user-error exit behavior; unrecoverable
execution or persistence failures use a distinct nonzero exit status.

## Scope and HTTP policy

Phase 1 accepts only these target forms:

```text
http://127.0.0.1:<port>/...
http://[::1]:<port>/...
https://127.0.0.1:<port>/...
https://[::1]:<port>/...
```

Reject hostnames, userinfo, unspecified addresses, IPv4-mapped IPv6,
noncanonical numeric IPv4 forms, control characters, and fragments. The
canonical origin is normalized scheme, literal host, and effective port.

The executor must make direct connections and bypass proxy environment
configuration. It must not rely on the calling environment being clean.

Only `GET` and `HEAD` are permitted. The executor sends a fixed User-Agent
and Accept header, generates Host from the canonical request URL, sends no
credentials or request body, ignores `Set-Cookie`, and keeps no cookie jar.
Planner-controlled headers are unsupported.

Redirects are handled manually. Before following each redirect, validate the
canonical target against the same literal-loopback origin, enforce a per-chain
redirect limit, detect loops, record the hop, and charge it to the request and
rate budgets. A redirect rejected after receiving a response is both a policy
rejection and a consumed request.

HTTPS verifies certificates by default. Self-signed development certificates
are out of scope; any future bypass requires an explicit recorded opt-in such
as `--tls-insecure`.

## Planner contract and loop

The planner receives only the target origin and normalized response
observations; all response text is untrusted data. It must return one of:

```json
{
  "type": "action",
  "action": {
    "tool": "http_request",
    "method": "GET",
    "path": "/example",
    "query": {"page": "1"},
    "purpose": "Inspect a same-origin linked page"
  }
}
```

```json
{
  "type": "complete",
  "reason": "No additional safe-method paths are useful"
}
```

Malformed JSON, wrong types, missing fields, and unknown fields are parser
errors and emit `planner_error`; they receive one corrective retry. Valid JSON
that contains a prohibited absolute URL, path beginning with `//`, fragment,
unsupported method, or non-scalar query is a proposed action that the scope or
policy layer rejects. A structured policy rejection is returned to the
planner, including a stable code, explanatory message, applicable limit or
allowed alternative, proposed value, and whether it is retryable. A small fixed
consecutive-error threshold ends the session.

After parser and policy validation, construct the existing action contract
only from canonical values:

```python
ToolAction(
    tool="http_request",
    target=canonical_origin,  # established session scope, never planner input
    parameters={
        "method": method,
        "path": normalized_path,
        "query": canonical_query,
    },
    purpose=purpose,
)
```

The loop is:

1. Validate scope and make an initial target request.
2. Normalize it into an observation.
3. Ask the planner to select one structured action or complete.
4. Validate scope and safe-method policy.
5. Execute accepted actions, record results and observations, then repeat.
6. Stop for model completion, budget/deadline, duplicate, error threshold, or
   operator interruption.

The initial request consumes one request but no planner decision.

## Accounting and timeouts

Maintain separate counters for:

- `decisions`: every planner response, including malformed, blocked, and
  duplicate proposals;
- `requests`: every HTTP exchange, including the initial request and redirect
  hops;
- `rejections`: policy and scope refusals;
- `consecutive_errors` and total runtime errors;
- redirect depth/loops; and
- monotonic wall-clock duration.

HTTP timeouts are clipped to the remaining monotonic deadline. With the
current synchronous generator interface, the duration limit is a soft bound
for a model call already in progress: no new model call or HTTP request begins
after expiry, but an uninterruptible generator call may overrun. Do not claim
a hard end-to-end duration limit until the generator interface supports
per-call deadlines and cancellation, including retry/backoff control.

Use fixed, documented Phase 1 defaults for request size, model-context size,
request rate, consecutive runtime errors, and total runtime errors.

HTTP 4xx/5xx responses are valid observations. Connection failures, HTTP
timeouts, oversized responses, and planner transport failures are runtime
errors. Policy rejections are not runtime errors; duplicate proposals consume
a decision and produce feedback or a duplicate stop reason.

Duplicate identity is the fingerprint of method, canonical origin, normalized
path, and canonical query representation. Query-key ordering cannot evade it;
GET and HEAD remain distinct. Redirect hops participate in redirect-loop
detection and request accounting, but do not automatically make a later
planner proposal duplicate.

## Evidence, events, and reporting

`AssessmentStore` SQLite state is authoritative. Workspace v0 assigns the
explicit per-run state location; committed state exports to ordered JSONL and a
human summary in the same run directory. Never create an undisclosed database
in the working directory.

Add an append-only versioned event table with at least:

```text
(session_id, sequence) UNIQUE
event_id UNIQUE
schema_version
event_type
timestamp
payload_json
```

When an operation updates existing action/observation records and writes an
event, commit them in one SQLite transaction. Preserve the existing store API
and tests; add events as a compatible layer.

The JSONL export uses committed events, ordered by `sequence`, with a shared
envelope:

```json
{
  "schema_version": 1,
  "sequence": 4,
  "timestamp": "...",
  "session_id": "...",
  "trace_id": "...",
  "type": "policy_decision",
  "data": {}
}
```

Required event types are:

```text
session_started
initial_request_planned
action_planned
policy_decision
http_result
observation
planner_error
session_finished
```

`ToolResult` remains execution data; an observation is a normalized claim
derived from it. Phase 1 observations can include status, content type, title,
same-origin links, and a body hash, but are never findings.

Same-origin link extraction is bounded context from the current response only.
Phase 1 has no crawl queue, recursive traversal, automatic metadata retrieval,
JavaScript fetching, form inventory, or automatic scheduling of extracted
links.

Store captured response bytes up to a fixed evidence cap. Evidence metadata
includes SHA-256 of captured bytes, artifact location, byte count, truncation
status, content type, requested/effective URL, status, elapsed time, and a
safe header subset. Never record authorization, proxy-authorization, or cookie
headers. A separate, lower model-context cap limits the normalized data given
to the planner.

Summary counters must be mechanically derived from event records. Rejections
never count as observations.

## Test plan

### In-repository unit tests

Cover literal-loopback validation, URL canonicalization, proxy bypass,
redirect validation/loops, scope and method rejection, budget accounting,
deadline behavior, duplicate fingerprints, malformed planner responses,
event transaction/order semantics, JSONL export, evidence truncation, and
CLI exit statuses.

### External BlackVault acceptance test

The BlackVault-owned driver lives in `~/xtests/blackvault`. It:

1. Sets `BLACKVAULT_DATA` to a temporary location before importing the app.
2. Starts BlackVault with an allocated loopback port using a target-owned
   `werkzeug.serving.make_server` launcher; it calls `init_db()` after import.
3. Waits for TCP readiness without adding an unaccounted assessment request.
4. Snapshots initialized database data, flag/vault-file hashes, upload listing,
   and other mutable state.
5. Records target traffic, distinguishing readiness, assessment, and cleanup.
6. Invokes the ordinary `vharness assess` CLI with a deterministic scripted
   OpenAI-compatible test endpoint.
7. Uses a plan containing two known-safe GETs, one rejected POST proposal, one
   rejected off-origin/absolute proposal, one canonical duplicate, and model
   completion.
8. Asserts only the allocated origin was contacted; no body or persistent
   cookies were sent; expected safe routes were used; rejected proposals made
   no network request; state snapshots match; and CLI, JSONL, SQLite, and
   traffic-accounting counters agree.
9. Stops the server process/group and removes temporary state in `finally`.

The deterministic acceptance test does not assess real model quality. A
separate manual live-model smoke run measures valid-first-response and
corrective-retry rates, action quality, policy-feedback usefulness, and
operator-facing log clarity.

## Implementation order

1. Complete the Workspace v0 prerequisite and its project-scoped run service.
2. Literal-loopback URL canonicalization and validation.
3. Direct HTTP executor with manual redirects, caps, and proxy bypass.
4. Transactional, versioned SQLite event persistence and ordered JSONL export.
5. Structured planner parser and assessment loop with precise counters and
   stop reasons.
6. CLI, human summary, and unit-test matrix.
7. External BlackVault acceptance driver.
8. Manual live-model smoke run.

## Completion criteria

Phase 1 is complete only when the generic loop operates without BlackVault
knowledge and the external acceptance test verifies that CLI counters, JSONL
records, SQLite events, recorded target requests, and pre/post target state
all agree.
