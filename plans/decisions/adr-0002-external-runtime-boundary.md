---
id: ADR-0002
title: Keep enforcement and authoritative validation outside Vharness
type: decision
status: accepted
owners: []
created: 2026-09-04
updated: 2026-09-04
depends_on: []
supersedes: []
related: [ARCH-0001, BENCH-0001]
---

# Keep enforcement and authoritative validation outside Vharness

## Context

A programmable agent harness is not an authoritative security boundary.
Prompts and harness logic can guide behavior but cannot reliably bind identity,
credentials, isolation, or allowed effects. Benchmark platforms already own
their target lifecycle and scoring.

## Decision

Vharness may reason, plan, and propose typed actions. The external runtime
executes or rejects them under its own identity, policy, credentials, and
isolation. External evaluators remain authoritative for task completion and
scores. Vharness consumes receipts from both and records them as evidence; it
does not recreate authorization checks, lifecycle control, audit enforcement,
or grading.

## Consequences

No credential-bearing executor belongs in the agent kernel. A receipt must be
correlated to its proposal and origin. Rejection, timeout, partial output, and
indeterminate completion are normal observations, not exceptional holes. The
operator establishes authorization before using Vharness.

## Alternatives considered

Harness-side policy gates and duplicate benchmark graders were rejected because
they create weaker, competing authorities and violate the repository boundary.

## Evidence and references

- NVIDIA trusted agent stack discussion supplied by the operator.
- Repository `AGENTS.md` operating and benchmark boundaries.

