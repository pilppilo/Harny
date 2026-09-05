---
id: ADR-0005
title: Use benchmark families as a capability engineering ladder
type: decision
status: accepted
owners: []
created: 2026-09-04
updated: 2026-09-04
depends_on: [ADR-0001, ADR-0003]
supersedes: []
related: [ARCH-0001, ROAD-0001, BENCH-0001, PHASE-0001, PHASE-0002, PHASE-0003, PHASE-0004]
---

# Use benchmark families as a capability engineering ladder

## Context

The product is a general-purpose long-horizon agent system, not an ARC,
Gymnasium, Hack The Box, or software-benchmark runner. The operator also requires
the software itself to become good at those environments and intends their
external results to guide engineering toward that capability.

## Decision

Gymnasium, ARC-AGI-3, operator-authorized Hack The Box labs, and software tasks
form an accumulating capability ladder. Their externally authoritative results
expose weaknesses in control, discovery, investigation, tool use, memory,
recovery, efficiency, and operator collaboration. Each rung has predeclared
targets and may support a labeled capability milestone. Evidence from later
rungs does not erase regressions on earlier ones.

The same general agent core, memory/context algorithms, supervision policy, and
operator protocol must cross the ladder. Benchmark identity may select only its
mechanical environment adapter and external evaluator. A weak result motivates a
general algorithm, architecture, or implementation experiment; it does not
authorize a hidden benchmark prompt or specialized core behavior.

No single score defines the product, and unrelated releases need not wait for
every rung. Claims are limited to the rungs actually demonstrated. The Vharness
Next redesign is not considered broadly capable or complete until the full
current ladder has externally supported evidence at its declared targets.

## Consequences

BENCH-0001 must define rung evidence, comparison procedures, and predeclared
tolerances without recreating external grading. Roadmap phases can ship honest
intermediate milestones while retaining the full-ladder goal. Product design
remains driven by transferable mechanisms rather than benchmark interfaces.

## Alternatives considered

Treating benchmarks as optional demonstrations was rejected because it provides
no disciplined path to the required capability. Making one aggregate benchmark
score the product goal was rejected because it hides domain regressions and
encourages specialization. Making every product release wait for the entire
ladder was rejected because it prevents useful, accurately labeled milestones.

## Evidence and references

- Operator direction in this planning session: the software must be good at the
  named environments, which serve as benchmarks and a ladder of goals rather
  than the product's defining purpose.
- ADR-0001 and ADR-0003 preserve one domain-neutral core.

