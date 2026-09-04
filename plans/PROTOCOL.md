# Plant planning protocol

Protocol version: 1.1

## 1. Purpose

Plant governs planning for projects where architecture, algorithms,
implementation, experiments, and validation evolve over many sessions and may
be handled by multiple humans or agents.

The protocol aims to make these questions answerable at any point:

1. What direction currently governs?
2. Which decisions are settled and which remain proposals?
3. What can be implemented now?
4. What evidence demonstrates completion?
5. Which document should be updated when new information arrives?

Plant is not an issue tracker and does not replace source control. It records
durable engineering intent, dependencies, and evidence.

## 2. Authority and precedence

The repository's explicit operator instructions and governing repository
instructions take precedence over Plant documents.

Within `plans/`, use this order when documents conflict:

1. Accepted architecture decisions (`ADR`).
2. Accepted governing architecture (`ARCH`).
3. Accepted benchmark and validation contracts (`BENCH`).
4. Accepted roadmaps and ready phase plans (`ROAD`, `PHASE`).
5. Active experiments (`EXP`) within their authorized scope.
6. Schematics (`SCHEM`) as views of governing documents.
7. Workstream logs (`WORK`) as non-authoritative observations.
8. Historical, inherited, draft, and proposed material.

The exception in §3 gives an index delivery-order table the authority of a
class-4 roadmap only while no accepted `ROAD` exists. No other index content
has independent planning authority.

Later dates do not automatically confer higher authority. A lower-authority
document cannot override a higher-authority document merely by being newer.

When a conflict is found:

1. Quote the conflicting text exactly.
2. Record the affected document IDs.
3. Stop work that depends on the unresolved choice.
4. Ask the operator or named decision owner which direction governs.
5. Record the resolution in an ADR before resuming dependent work.

## 3. Authoritative index

Every adopted repository must have `plans/README.md`. It is the routing index,
not a duplicate specification. Its delivery-order table is a projection of an
accepted `ROAD`; when no `ROAD` is accepted, that table is normative for phase
order and carries the class-4 roadmap authority defined in §2. The Current
focus block is a maintained routing convenience, not a separate authority
source.

Every non-`None` Current focus entry must name stable document IDs. `Now`
names a `PHASE` that is `ready` or `implementing`, or an `EXP` that is
`running`; `Read` names its governing context and direct dependencies; and
`Workstream` names an `active` `WORK` log when one exists.

The index must contain:

- The governing architecture and protocol version.
- Decisions and their status.
- Active roadmap and phases in dependency order.
- A Current focus block with Now, Read, Workstream, Next, and Blocked IDs.
- ID reservations, including retired IDs.
- Active benchmark contracts.
- Active experiments and workstreams.
- Known blocked decisions.
- Inherited or historical documents and their current role.

If a document is not indexed, agents must treat it as unclassified reference
material until its role is established.

## 4. Document types and identifiers

Use stable identifiers that remain unchanged if a file is renamed.

| Prefix | Type | Purpose |
| --- | --- | --- |
| `ARCH` | Architecture | Governing system structure, contracts, or algorithms |
| `ROAD` | Roadmap | Ordered product or architecture delivery strategy |
| `PHASE` | Phase | Implementable work with entrance and exit criteria |
| `ADR` | Decision | One durable architectural or product decision |
| `BENCH` | Benchmark | External evaluation contract and evidence requirements |
| `EXP` | Experiment | Time-bounded investigation of an unresolved question |
| `SCHEM` | Schematic | Searchable visual projection of accepted design |
| `WORK` | Workstream | Append-only coordination and implementation discoveries |

Identifiers use a four-digit repository-wide sequence within each type, such
as `ARCH-0001` or `ADR-0012`. Never reuse an identifier.

Before drafting a governed document, reserve its unused ID in the index. The
reservation lists its type, owner, purpose, timestamp, and status. Remove an
`active` reservation in the same change that adds the document to the index.
If drafting is abandoned, mark the reservation `retired`; retired IDs are
never reused.

File names use lowercase kebab case and begin with the lowercase identifier:

```text
architecture/arch-0001-system.md
decisions/adr-0001-external-execution-boundary.md
phases/phase-0001-event-foundation.md
```

## 5. Frontmatter

Every governed document starts with YAML frontmatter containing:

```yaml
---
id: ARCH-0001
title: System architecture
type: architecture
status: proposed
owners: [architecture]
created: 2026-09-04
updated: 2026-09-04
depends_on: []
supersedes: []
related: []
---
```

Dates use ISO 8601. References use stable document IDs rather than file names.
The metadata shape is described by `schema/metadata.schema.json`.
For dependency-free validation, use the templates' flat frontmatter form:
single-line scalars and bracketed lists; multiline YAML values are unsupported.

## 6. Status lifecycles

### Architecture, roadmap, and benchmark documents

```text
draft -> proposed -> accepted -> superseded
                  \-> rejected
```

### Phase documents

```text
draft -> proposed -> accepted -> ready -> implementing
                                      -> blocked
implementing -> implemented -> verified
implementing -> blocked
implemented -> implementing  # verification found required work
any active state -> superseded
```

Definitions:

- `accepted`: direction is approved, but dependencies may remain.
- `ready`: entrance criteria and dependencies are satisfied.
- `implemented`: scoped code and documentation changes exist.
- `verified`: every exit criterion has linked evidence.
- `blocked`: progress requires an external decision or unavailable dependency.

### Decisions

```text
proposed -> accepted
         -> rejected
accepted -> superseded
```

Accepted ADR text is immutable except for corrections that do not change its
meaning. A changed decision requires a new ADR that lists the old ADR under
`supersedes`.

### Experiments

```text
draft -> planned -> running -> completed
                           \-> abandoned
```

An experiment result is evidence, not automatically an architecture decision.
Promote its conclusion through an ADR or architecture change.

### Workstreams and schematics

Workstreams are `active` or `closed`. Schematics are `draft`, `current`, or
`superseded` and must identify the governing documents they project.

## 7. Required contents

### Architecture

An architecture document must state:

- Problem and scope.
- Goals and non-goals.
- Invariants.
- Components and responsibility boundaries.
- Public contracts and ownership of state.
- Control flow and failure behavior.
- Persistence, recovery, and compatibility expectations.
- Performance and scaling assumptions.
- Security or external-system boundaries where relevant.
- Alternatives and unresolved questions.
- Related decisions, schematics, and phases.

Algorithm specifications must additionally include inputs, outputs,
invariants, computational cost, determinism requirements, tunable parameters,
failure modes, and evaluation strategy.

### Phase

A phase must be independently implementable and include:

- Outcome stated in observable terms.
- Dependencies and entrance criteria.
- In-scope and out-of-scope work.
- Contracts added or changed.
- Ordered implementation work.
- Migration and compatibility effects.
- Test strategy.
- Exit criteria with required evidence.
- Risks and rollback or recovery approach.

Do not use percentage-complete estimates. A phase is assessed through its exit
criteria.

### Benchmark

A benchmark contract must distinguish:

- The product behavior under evaluation.
- The external system that owns environments and authoritative scoring.
- Inputs and observations visible to the product.
- Actions counted by the benchmark.
- Seeds, versions, datasets, and contamination boundaries.
- Efficiency, cost, reliability, and completion measurements.
- Repetition and statistical reporting.
- Evidence required to reproduce or audit a claim.

Do not recreate an external benchmark's grader inside the product.

### Experiment

An experiment must state a falsifiable question, baseline, controlled changes,
measurement method, stopping rule, artifact locations, and the decision it is
intended to inform.

### Workstream

A workstream is append-only. Each entry records:

- Timestamp and author or agent.
- Goal.
- Work completed.
- Evidence.
- Discoveries affecting later work.
- Open questions.
- Suggested next action.

Any unresolved question or suggested next action that remains relevant must be
copied forward into each subsequent entry until resolved or explicitly dropped.
For this purpose, an item is closed only when resolved or explicitly dropped;
a workstream is closed only once it has no open items. A verified phase does
not by itself close its workstream.

Routine command output belongs in run artifacts, not workstream documents.

## 8. Dependency and readiness rules

Dependencies form a directed acyclic graph.

- A document cannot depend on itself.
- Circular dependencies are invalid.
- A phase cannot become `ready` unless each required architecture, decision,
  and earlier phase dependency is accepted or verified as appropriate.
- For a phase's required dependencies: `ARCH`, `ADR`, `ROAD`, and `BENCH`
  must be `accepted`; an earlier `PHASE` must be `verified`; and a required
  `EXP` must be `completed`. `SCHEM` and `WORK` are never phase dependencies.
- A dependent phase returns to `blocked` or `proposed` if a governing
  dependency is superseded in a materially incompatible way.
- Optional dependencies must be labeled in prose and must not silently become
  entrance criteria.

## 9. Traceability

Trace decisions in both directions:

```text
operator goal
  -> ADR / governing architecture
  -> roadmap phase
  -> implementation commit or change set
  -> tests and external benchmark evidence
  -> verified phase
```

Architecture documents list implementing phases. Phase documents list their
governing architecture and decisions. Verification entries link exact test,
benchmark, report, or artifact identifiers.

Claims such as "complete," "correct," "faster," or "general" require linked
evidence and the conditions under which the evidence was produced.

## 10. Schematics

Schematics are projections, not separate sources of architectural truth.

- Prefer Mermaid in Markdown and embed it in its governing document unless the
  view spans multiple governing documents or needs an independent lifecycle.
- Put the schematic ID and governing document IDs in frontmatter.
- Update a schematic in the same change that materially changes its governing
  architecture.
- Label unresolved branches as proposals.
- Do not hide failure paths, external boundaries, or state ownership merely to
  simplify a diagram.

## 11. Human and agent collaboration

The human operator remains the product-direction authority. Agents may draft,
analyze, implement accepted phases, and record evidence within the scope they
are given.

Before implementation work, an agent must read:

1. Repository instructions.
2. `plans/README.md`.
3. The active plan named in Current focus and the documents listed under Read.
4. The eight most recent entries in the active workstream indexed for its
   task, if one exists, using the copy-forward rule in §7.

Agents must not scan `plans/`, templates, or the schema for implementation
context. Read `plans/PROTOCOL.md` completely only before creating or changing
a governed planning document, or while resolving a planning conflict.

Coordination rules:

- Prefer one active editor per governed document.
- Divide parallel work by document or module boundary.
- Record cross-cutting discoveries in the appropriate workstream.
- Send concise references by document ID instead of copying specifications.
- Do not use a worklog entry to change architecture.
- Do not silently resolve conflicting plans.
- A human correction is recorded in the relevant ADR or governing document so
  later agents do not depend on conversational history.

## 12. Change protocol

For a material planning change:

1. Identify affected governing documents and dependents.
2. Add or update the ADR when a durable choice changes.
3. Update architecture and algorithms.
4. Update affected schematics.
5. Reassess phase readiness and benchmark coverage.
6. Update the plan index.
7. Record the change in the relevant workstream.

Any status change to an indexed document must update its index row in the same
change. If it affects a document named in Current focus, or changes which work
is Now, Next, or Blocked, update that block in the same change.

Do not edit historical evidence to make it agree with the new decision.

## 13. Quality gate

Before accepting a governing document, confirm:

- Its responsibility boundaries are unambiguous.
- State ownership and failure behavior are explicit.
- Algorithms have measurable evaluation criteria.
- External responsibilities are not duplicated.
- Dependencies are complete and acyclic.
- Compatibility and migration effects are addressed.
- Schematics agree with the prose.
- Open questions are visible.
- Implementing phases can be verified objectively.

Before marking a phase verified, confirm:

- Every exit criterion has evidence.
- Relevant tests pass from a clean environment.
- Failure and restart paths were exercised where applicable.
- Performance claims include baselines and run conditions.
- External benchmark claims use results from the authoritative system.
- Documentation and schematics match the implementation.

## 14. Scaling without bureaucracy

Use the smallest document set that preserves clarity.

- A small isolated change may need only one accepted phase.
- A reversible experiment does not need a new architecture document.
- A cross-cutting invariant or responsibility-boundary change requires an ADR.
- Split a document when independent sections acquire different owners,
  lifecycles, or implementation dependencies.
- Do not duplicate requirements across files; link to the authoritative source.
