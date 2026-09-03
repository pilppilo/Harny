# Dynamic Web Assessment and CTF Plan

## Current implementation boundary

`dynamic-safe-method-assessment.md` is the binding Phase 1 specification.
`workspace-project-foundation.md` is its completed prerequisite implementation
milestone. Workspace v0 provides local run organization only; it does not grant
assessment scope or policy authority. The safe-method assessment is the next
implementation milestone.
Where this roadmap describes manifests, DNS names, crawling, OPTIONS, resume,
concurrency, multiple agents, findings, CTF objectives, or active validation,
that behavior is post-Phase 1. Phase 1 derives and persists an immutable
internal scope snapshot from its CLI target and fixed safe-method policy; it
does not accept a user-authored manifest.

## Purpose

Evolve vharness from a static, source-oriented SAST harness into an
authorization-first dynamic web assessment framework. The existing static
workflow remains supported:

```text
vharness scan <source-dir>       # existing SAST workflow
vharness assess <target> ...     # scoped dynamic web/CTF workflow
```

The dynamic workflow is for local or explicitly authorized targets. It will
perform bounded reconnaissance, persist every decision and response,
coordinate specialized agents, build an asset and endpoint map, and record
CTF findings or flags as validated evidence rather than unverified model
output.

## Research basis

The architecture follows OWASP's distinction between passive application
understanding and active testing. It starts by mapping entry points, page
content, JavaScript assets, APIs, and execution paths before any later
validation capability is considered.

- OWASP Web Security Testing Guide: https://wstg.owasp.org/
- OWASP information gathering: https://wstg.owasp.org/latest/4-Web_Application_Security_Testing/01-Information_Gathering/
- OWASP entry-point identification: https://wstg.owasp.org/latest/4-Web_Application_Security_Testing/01-Information_Gathering/06-Identify_Application_Entry_Points/
- OWASP API Security Top 10: https://owasp.org/API-Security/editions/2023/en/0x10-api-security-risks/

## Current foundation

The repository already has the beginnings of this transition:

- `src/vharness/tools.py` defines typed `ToolAction`, `ToolResult`, and a tool
  registry.
- `src/vharness/assessment.py` provides a durable SQLite session, action, and
  observation ledger with action fingerprints.
- `plans/transition.md` describes the initial safety principles and phased
  direction.

These components are not yet connected to scope/policy enforcement, HTTP
execution, agent orchestration, CLI commands, asset tracking, or reporting.
They should become a distinct assessment workflow instead of being forced
into the batch SAST `Probe -> Generator -> Detector` runner.

## Target architecture (post-Phase 1)

```text
Specialist agents -> structured proposed actions
                          |
                          v
                  central policy engine
                          |
                          v
                  approved tool executor
                          |
                          v
SQLite session ledger + evidence artifacts
                          |
                          v
  assets / hypotheses / validated findings / CTF status
                          |
                          v
           planner receives normalized observations
```

Agents must never receive unrestricted shell or network access. They may only
propose a typed, allowlisted action. A central executor verifies scope,
budgets, duplicate status, redirect destinations, and policy tier before it
performs the action.

Phase 1 deliberately uses the smaller sequential flow below; it introduces no
specialist-agent or coordination abstraction:

```text
single planner -> typed proposal -> fixed scope/policy -> HTTP executor
      ^                                                        |
      +---------------- normalized observation <- evidence ---+
```

## Post-Phase-1 reconnaissance tools

Implement these capabilities first:

- `http_fetch`: bounded `GET`, `HEAD`, and optionally `OPTIONS`; record status,
  headers, redirect chain, body hash, title, and a bounded body excerpt.
- `metadata_fetch`: retrieve explicitly allowed standard paths such as
  `robots.txt`, `sitemap.xml`, manifests, and known API descriptions.
- `link_extract`: parse same-origin links, forms, scripts, and static assets
  from already fetched responses.
- `js_route_extract`: discover client-side routes and API hints from fetched
  JavaScript without executing it.
- `endpoint_inventory`: consolidate routes, methods, parameters, forms,
  cookies, technologies, and source evidence.
- Later, `browser_observe`: an isolated browser profile visits approved pages
  and records browser-observed requests. It does not use saved browser sessions
  or arbitrary user credentials by default.

## Agent and sub-agent model (post-Phase 1)

Use application-level agent roles with narrow responsibilities:

| Role | Responsibility | Permitted output |
| --- | --- | --- |
| Coordinator | owns session objective and work queue | delegation, stop, summary |
| Surface recon | maps pages, redirects, metadata, links, and forms | passive fetch/crawl proposals |
| API agent | inventories documented and observed APIs | safe observation proposals |
| Client agent | analyzes fetched JS and browser observations | route/asset proposals |
| CTF hypothesis agent | connects evidence to challenge objectives | hypotheses only |
| Verification agent | independently verifies enough evidence | bounded repeat observations |
| Reporter | produces the evidence-backed report | no network actions |

Each sub-agent receives only a narrow task, selected observations, remaining
budget, and an explicit allowed-action set. It returns structured proposals,
not shell commands. The coordinator prevents repeated work through action
fingerprints and stops branches when the objective, budget, or evidence
threshold is met.

## Scope and policy model (post-Phase 1)

Require an assessment manifest before any network action in the broader
roadmap:

```toml
[scope]
authorized = true
targets = ["http://127.0.0.1:3000"]
allowed_hosts = ["127.0.0.1"]
allowed_cidrs = ["127.0.0.0/8"]
allowed_methods = ["GET", "HEAD"]
mode = "passive"

[budgets]
max_actions = 200
max_requests_per_host = 120
requests_per_second = 2
max_response_bytes = 1048576
max_depth = 3
max_session_minutes = 30
```

Enforce the following in code, not through agent prompts:

- Canonicalize URLs and validate every redirect hop before connecting.
- Resolve and validate the eventual IP address on every connection to prevent
  hostname, redirect, and DNS-rebinding scope bypasses.
- Disable inherited proxy settings unless the manifest explicitly permits one.
- Block Docker, localhost, and private ranges unless explicitly listed; this
  lets local CTF labs opt in without making them the global default.
- Enforce host, method, rate, request-count, response-size, time,
  crawl-depth, and concurrency limits.
- Redact authorization headers, cookies, tokens, and probable secrets from
  normal logs and model context.
- Store raw evidence as access-controlled, content-addressed artifacts; logs
  contain hashes and bounded summaries.
- Separate `passive`, `validated`, and `active-lab` tiers. The first broader
  roadmap release exposes only passive actions. State-changing or exploit-style
  CTF actions require explicit lab authorization and operator approval in a
  later tier. Do not use `passive` as an alias for the Phase 1 GET/HEAD
  safe-method policy: target handlers can mutate state on those methods.

## Persistent data model (post-Phase 1)

Keep SQLite as the durable source of truth and add an exportable JSONL event
stream. Extend the current assessment store with:

- `scopes`: immutable snapshot of the manifest used for the session.
- `policy_decisions`: action, approval/rejection, reason, and limits applied.
- `assets`: hosts, services, applications, endpoints, parameters, and JS assets.
- `artifacts`: content hash, media type, byte count, redaction metadata, and path.
- `hypotheses`: confidence, evidence references, and open/verified/rejected state.
- `findings`: severity, CWE/OWASP category, reproducibility, and evidence links.
- `agent_tasks`: parent task, assigned role, budget, lifecycle, and summary.
- `ctf_objectives`: challenge objective, validation state, and flag evidence hash.

Action and observation records should also include agent identity, policy tier,
parent task ID, request/response artifact references, and a schema version.

## Post-Phase-1 implementation phases

### 1. Generalize the assessment foundation

- Formalize `AssessmentScope`, action schemas, policy decisions, artifact
  references, and SQLite schema migrations.
- Add `assessment init`, `status`, `resume`, `export`, and `stop` CLI commands.
- Keep the existing SAST runner independent; share only common logging and
  configuration utilities.

### 2. Generalize policy before networking

- Build URL/IP/redirect scope checks, allowlisted methods, budgets, approvals,
  duplicate suppression, and secret redaction.
- Add scope-bypass tests before any real HTTP transport is introduced.

### 3. Add passive HTTP reconnaissance

- Add a bounded asynchronous HTTP client with explicit redirect handling.
- Normalize responses, retrieve approved metadata, parse HTML, discover JS
  assets, and maintain a same-origin crawl queue.
- Persist every result as an observation plus an evidence artifact.

### 4. Build the asset graph and reports

- Derive endpoint, parameter, form, and API inventories from observations.
- Produce dynamic-assessment Markdown and JSON reports containing scope,
  policy decisions, coverage, evidence, and explicit unknowns.

### 5. Add controlled multi-agent orchestration

- Add structured planner proposals, role-specific contexts, task queues,
  deduplication, checkpoint/resume, and termination rules.
- Start with deterministic and mock planners in tests; make live model planning
  opt-in.

### 6. Add the CTF-lab workflow

- Add objective tracking and an evidence-verification gate for a solved
  challenge or flag.
- Keep findings as hypotheses until independently corroborated.
- Do not add `active-lab` capabilities until the passive workflow, approval
  gates, audit record, and local-lab integration tests are complete.

### 7. Optional browser and advanced validation

- Add isolated browser observation behind an optional dependency.
- Treat authenticated flows, form submission, fuzzing, and other state changes
  as separately approved capabilities, never defaults.

## Later roadmap testing and acceptance criteria

Use local fixture applications and mock DNS/HTTP transports; never require a
public target for tests.

- Reject out-of-scope hosts, ports, schemes, paths, IP literals, redirects,
  encoded URLs, user-info URLs, and DNS-rebinding attempts.
- Verify rate, depth, response-size, timeout, duplicate-action, interruption,
  and resume behavior.
- Verify that cookies, authorization headers, and tokens do not enter planner
  context or ordinary logs.
- Test redirects, malformed HTML, compressed bodies, non-HTML assets, relative
  links, SPA routes, and API-description documents.
- Verify agents cannot execute actions directly and all proposals pass through
  the policy engine.
- Require every reported asset, finding, or CTF success to trace to action IDs
  and evidence artifacts.
- Preserve and run all existing `scan`, `eval`, replay, JSONL logging, and
  plugin-registration tests.

The broader dynamic roadmap release is complete when `vharness assess` can
safely map an explicitly allowed local web app, stop and resume
deterministically, produce an evidence-linked inventory, and leave a complete
policy and action log, without active exploitation capability. Phase 1
acceptance criteria are defined only in `dynamic-safe-method-assessment.md`.

## Default product boundary

Use local or explicitly authorized lab targets only, passive reconnaissance by
default, and a separate approved `active-lab` tier for any CTF-solving action
that goes beyond observation.
