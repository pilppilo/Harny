---
id: SCHEM-0001
title: Vharness Next system and control flow
type: schematic
status: current
owners: []
created: 2026-09-04
updated: 2026-09-04
depends_on: [ARCH-0001, ADR-0001, ADR-0002, ADR-0003, ADR-0004, ADR-0005]
supersedes: []
related: [ROAD-0001, PHASE-0001, PHASE-0002, PHASE-0003, PHASE-0004]
---

# Vharness Next system and control flow

This cross-document view represents ARCH-0001 and ADR-0001 through ADR-0005.
Arrows crossing the runtime boundary are proposals and receipts, never direct
Vharness execution authority.

```mermaid
flowchart TB
    Human[Human operator] -->|durable messages and controls| UI[Interaction surface]
    UI --> Coordinator[Session coordinator]
    Coordinator --> Objective[Versioned objective]
    Coordinator --> Journal[(Append-only event journal)]
    Journal --> Projections[Rebuildable memory projections]
    Projections --> Context[Deterministic context assembler]
    Context --> Agent[General agent kernel]
    Agent -->|typed result| Coordinator

    Journal --> Monitor[Progress monitor]
    Monitor -->|trigger and bounded digest| Supervisor[Advisory supervisor]
    Supervisor -->|guidance event; no tools| Coordinator
    Journal --> Attempts[All variation attempts]
    Journal --> Lineage[Externally accepted single lineage]
    Attempts --> Promotion[Applicability and stale-head check]
    Promotion -->|current externally accepted evaluation only| Lineage

    Coordinator -->|ActionProposal| Runtime[External controlled runtime]
    Runtime -->|ExecutionReceipt| Coordinator
    Runtime --> Environment[External environment or target]
    Environment -->|Observation| Coordinator
    Coordinator -->|evaluation request| Evaluator[External evaluator]
    Evaluator -->|authoritative EvaluationReceipt| Coordinator
    Coordinator --> Promotion

    RuntimeBoundary{{identity / policy / credentials / isolation / execution}}
    Runtime --- RuntimeBoundary
    ValidationBoundary{{lifecycle / authoritative validation and scoring}}
    Environment --- ValidationBoundary
    Evaluator --- ValidationBoundary
```

```mermaid
stateDiagram-v2
    [*] --> Created
    Created --> Running: start
    Running --> Paused: operator pause
    Paused --> Running: operator resume
    Running --> Stopping: operator stop
    Paused --> Stopping: operator stop
    Running --> Completed: externally supported completion
    Running --> Failed: unrecoverable internal integrity failure
    Stopping --> Stopped: checkpoint and settle
    Completed --> [*]
    Failed --> [*]
    Stopped --> [*]
```

## Notes and unresolved branches

The initial coordinator has one event writer, at most one unresolved
state-changing proposal per session, and one committed lineage. An attempt may
span many actions; only external acceptance advances lineage. Population/archive
branching is deferred. No unresolved branch blocks PHASE-0001.
