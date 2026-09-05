# Vharness library implementation specification

This directory specifies **Python code design** for the accepted Vharness Next
architecture: module ownership, types, callable contracts, transaction boundaries,
and tests. It is a handoff for an implementing model, not a new product roadmap.

Prepared against repository revision
`688b44c5d5652f722a3f086f95a490685bc12196`. Recheck the working tree before use.

## Read order

1. Repository [AGENTS.md](../../AGENTS.md).
2. [Planning index](../../plans/README.md) and its Current focus documents.
3. [Library structure](01-library-structure.md).
4. [Types and callable contracts](02-contracts.md).
5. [Persistence and execution](03-persistence-and-execution.md).
6. [Later capability modules](04-capability-modules.md).
7. [Implementation and verification](05-implementation-and-verification.md).

## Authority and scope

The user explicitly requested these specifications under `specs/proto` and asked
that `plans` remain unchanged. These are implementation details subordinate to
the accepted plans, not additional Plant-governed documents. Do not edit the
planning index, decisions, phase statuses, workstream, or completion criteria as
part of this handoff. If a future implementation task still has the same
restriction, report implementation evidence separately; do not claim a phase has
been formally verified or change its status.

The governing sources are ARCH-0001, ADR-0001 through ADR-0005, ROAD-0001,
BENCH-0001, and the applicable phase. If a specification and governing document
conflict, quote both exact passages and ask which governs before implementing
the dependent behavior. Do not silently reinterpret either document.

PHASE-0001 is the immediate implementation target. The later-module document
defines how subsequent capabilities fit the library; it does not authorize
skipping phase prerequisites or creating empty scaffolding. Numeric supervisor
policy remains subject to the experiment required by PHASE-0003.

## Required implementation character

- A cohesive Python library with a thin CLI; no script containing the system.
- Explicit dependencies, typed records, deterministic domain functions, and
  infrastructure isolated behind narrow boundaries.
- One local process and one coordinator writer initially, as already specified.
- External runtime and evaluator connections exchange proposals and receipts;
  they do not replace external authorization, lifecycle, auditing, or grading.
- Preserve existing entry points and the legacy pipeline while adding the new
  package beside them.
- Use Black, Pylint, and pytest. A clean linter result complements design review;
  it does not establish architecture or behavioral correctness.

## Handoff instruction

Implement the currently authorized phase using this code specification and its
governing plan. Inspect existing configuration and tests first. Build the library
and test it directly, then add the thin entry point. Record exact checks and
limitations in the implementation handoff. Do not rewrite unrelated legacy code,
invent external services, or implement later capabilities merely because their
interfaces are described here.
