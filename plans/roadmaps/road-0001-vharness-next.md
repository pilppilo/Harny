---
id: ROAD-0001
title: Deliver the Vharness Next AVO-inspired redesign
type: roadmap
status: accepted
owners: []
created: 2026-09-04
updated: 2026-09-04
depends_on: [ARCH-0001, ADR-0001, ADR-0002, ADR-0003, ADR-0004, ADR-0005, BENCH-0001]
supersedes: []
related: [PHASE-0001, PHASE-0002, PHASE-0003, PHASE-0004]
---

# Deliver the Vharness Next AVO-inspired redesign

## Product outcome

Vharness Next is a resumable, human-steerable agent system that makes
measurable long-horizon progress through external tools and feedback. One
agent architecture operates across authorized recon and assessment,
interactive reasoning, Gymnasium control tasks, and software work.
It must become strong at the software, Gymnasium, ARC-AGI-3, and authorized HTB
capability rungs without making any benchmark the product's identity.

## Governing architecture and decisions

ARCH-0001 defines the system. ADR-0001 through ADR-0005 fix the core direction.
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
7. Use benchmark rungs to drive transferable improvements and label intermediate
   capability honestly rather than hiding gaps behind one aggregate score.

## Ordered phases

| Order | Phase | Dependencies | Observable outcome |
| --- | --- | --- | --- |
| 1 | PHASE-0001 | Accepted architecture, decisions, roadmap, benchmark | A session preserves multi-action attempts and advances a single committed lineage only from external acceptance while remaining resumable |
| 2 | PHASE-0002 | PHASE-0001 verified | The agent autonomously consults lineage and knowledge, acts, debugs, and evaluates within bounded attempts using deterministic context and live operator steering |
| 3 | PHASE-0003 | PHASE-0002 verified | The system distinguishes productive plateaus from stagnation, obtains advisory supervision, and recovers through attributable new attempts |
| 4 | PHASE-0004 | PHASE-0003 verified | External benchmark evidence shows the unchanged core working across all target environment families |

## Cross-phase invariants

- The event journal is canonical; summaries and indexes are rebuildable.
- Vharness proposes actions; an external runtime executes or rejects them.
- External systems remain authoritative for lifecycle and evaluation.
- The human operator is represented in durable state and current context.
- Environment adapters contain serialization and protocol mechanics only.
- Unsuccessful attempts remain durable history but never enter committed lineage.
- Every externally visible action and receipt has a stable correlation ID.
- A process crash cannot cause blind replay of an indeterminate action.

## Benchmark progression

PHASE-0001 uses contract, attempt/commit, and crash/replay tests. PHASE-0002 adds
small deterministic Gymnasium and software fixtures plus agent-directed access
to lineage, knowledge, and evaluation. PHASE-0003 experimentally selects
supervision policy and adds seeded plateau, stagnation, and recovery trials.
PHASE-0004 advances the software, Gymnasium, ARC-AGI-3, and authorized HTB rungs
in BENCH-0001, retaining earlier rungs as regression coverage and publishing raw
receipts plus per-rung results.

## Compatibility and migration strategy

Build the new kernel alongside the current entry points. Reuse existing code
only behind an accepted contract. Do not perform a broad rewrite or migrate
historical session state. Intermediate releases identify the capability rungs
actually demonstrated. Once PHASE-0004 is verified, make the new kernel the
default through one reversible entry-point change; removal of the old path is a
later explicit phase.

## Risks and decision points

The largest risks are lossy memory, uncontrolled context growth, false
stagnation signals, adapter leakage into policy, and unverifiable benchmark
claims. Each is addressed by durable raw events, deterministic selection,
hysteresis, contract tests, and external evidence. Distributed execution,
vector databases, multi-agent swarms, and learned routing remain out until a
measured ceiling requires them.

## Completion definition

The redesign is complete when every phase is verified, the same core achieves
BENCH-0001's complete current capability ladder at predeclared targets, sessions
resume after injected failures without duplicate effects, the operator can
inspect and steer live work, and the external runtime/evaluator boundary is
demonstrated rather than assumed.
