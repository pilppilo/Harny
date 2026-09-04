---
id: ROAD-0001
title: Deliver the Vharness Next AVO-inspired redesign
type: roadmap
status: accepted
owners: []
created: 2026-09-04
updated: 2026-09-04
depends_on: [ARCH-0001, ADR-0001, ADR-0002, ADR-0003, ADR-0004, BENCH-0001]
supersedes: []
related: [PHASE-0001, PHASE-0002, PHASE-0003, PHASE-0004]
---

# Deliver the Vharness Next AVO-inspired redesign

## Product outcome

Vharness Next is a resumable, human-steerable agent system that makes
measurable long-horizon progress through external tools and feedback. One
agent architecture operates across authorized recon and assessment,
interactive reasoning, Gymnasium control tasks, and software work.

## Governing architecture and decisions

ARCH-0001 defines the system. ADR-0001 through ADR-0004 fix the core direction.
BENCH-0001 defines evidence required to claim progress. Inherited plans are
reference material only, as classified by `plans/README.md`.

## Current baseline

The branch contains the existing Vharness implementation and inherited plans,
but not the accepted session journal, general environment contract, memory
projections, supervisor, or cross-domain evidence specified here. No existing
component is presumed reusable until PHASE-0001 maps it to an accepted contract.

## Delivery principles

1. Establish durable truth and narrow contracts before autonomous behavior.
2. Keep the first implementation single-process and standard-library-first.
3. Build operator observation and steering into the kernel from the start.
4. Add algorithmic complexity only after benchmark or failure evidence.
5. Preserve an executable vertical slice at each phase boundary.
6. Compare the same agent core across environments; change only adapters.

## Ordered phases

| Order | Phase | Dependencies | Observable outcome |
| --- | --- | --- | --- |
| 1 | PHASE-0001 | Accepted architecture, decisions, roadmap, benchmark | A session can propose, receive, journal, pause, resume, and reconcile actions without executing them internally |
| 2 | PHASE-0002 | PHASE-0001 verified | The agent completes bounded tasks with deterministic context, durable memory, and live operator steering |
| 3 | PHASE-0003 | PHASE-0002 verified | The system detects stagnation, obtains advisory supervision, recovers, and preserves candidate/trajectory lineage |
| 4 | PHASE-0004 | PHASE-0003 verified | External benchmark evidence shows the unchanged core working across all target environment families |

## Cross-phase invariants

- The event journal is canonical; summaries and indexes are rebuildable.
- Vharness proposes actions; an external runtime executes or rejects them.
- External systems remain authoritative for lifecycle and evaluation.
- The human operator is represented in durable state and current context.
- Environment adapters contain serialization and protocol mechanics only.
- Every externally visible action and receipt has a stable correlation ID.
- A process crash cannot cause blind replay of an indeterminate action.

## Benchmark progression

PHASE-0001 uses contract conformance and crash/replay tests. PHASE-0002 adds
small deterministic Gymnasium and software fixtures. PHASE-0003 adds seeded
stagnation and recovery trials. PHASE-0004 runs the externally owned suites in
BENCH-0001 and publishes raw receipts plus aggregate results.

## Compatibility and migration strategy

Build the new kernel alongside the current entry points. Reuse existing code
only behind an accepted contract. Do not perform a broad rewrite or migrate
historical session state. Once PHASE-0004 is verified, make the new kernel the
default through one reversible entry-point change; removal of the old path is
a later explicit phase.

## Risks and decision points

The largest risks are lossy memory, uncontrolled context growth, false
stagnation signals, adapter leakage into policy, and unverifiable benchmark
claims. Each is addressed by durable raw events, deterministic selection,
hysteresis, contract tests, and external evidence. Distributed execution,
vector databases, multi-agent swarms, and learned routing remain out until a
measured ceiling requires them.

## Completion definition

The redesign is complete when every phase is verified, the same core passes
BENCH-0001's generality gate, sessions resume after injected failures without
duplicate effects, the operator can inspect and steer live work, and the
external runtime/evaluator boundary is demonstrated rather than assumed.

