# Vharness Next planning index

Protocol: Plant v1.1 (`plans/PROTOCOL.md`)

Plant source revision: 712f419

The protocol, schema, and templates are a pinned snapshot created from the
independent Plant project on 2026-09-04. Plant remains a separate repository.

This file is the authoritative router for Vharness Next planning. Read the
documents named under **Current focus** before implementation; do not infer
current direction from inherited plans.

## Current focus

- **Now:** PHASE-0001 — ready.
- **Read:** ARCH-0001, ADR-0001, ADR-0002, ADR-0003, ADR-0004, ADR-0005, ROAD-0001, BENCH-0001.
- **Workstream:** WORK-0001.
- **Next:** PHASE-0002.
- **Blocked:** None.

## ID reservations

None.

## Governing direction

| ID | Document | Status | Purpose |
| --- | --- | --- | --- |
| ARCH-0001 | `architecture/arch-0001-avo-inspired-agent-system.md` | accepted | Vharness Next architecture, contracts, state, algorithms, and boundaries |
| ROAD-0001 | `roadmaps/road-0001-vharness-next.md` | accepted | Ordered delivery of the redesign |
| SCHEM-0001 | `schematics/schem-0001-system-and-control-flow.md` | current | Searchable cross-document system and control-flow view |

## Decisions

| ID | Status | Decision | Supersedes |
| --- | --- | --- | --- |
| ADR-0001 | accepted | Build one AVO-inspired, domain-neutral agent core | — |
| ADR-0002 | accepted | Keep execution enforcement and authoritative validation outside Vharness | — |
| ADR-0003 | accepted | Use environment contracts, not benchmark-specific behavioral profiles | — |
| ADR-0004 | accepted | Make the human operator a durable, first-class participant | — |
| ADR-0005 | accepted | Use benchmark families as a capability engineering ladder | — |

## Delivery order

| Order | ID | Status | Depends on | Outcome |
| --- | --- | --- | --- | --- |
| 1 | PHASE-0001 | ready | ARCH-0001, ROAD-0001, BENCH-0001, ADR-0001..0005 | Resumable session kernel, attempt history, committed lineage, and external contracts |
| 2 | PHASE-0002 | accepted | PHASE-0001 | Autonomous variation loop, memory, context, and live human interaction |
| 3 | PHASE-0003 | accepted | PHASE-0002 | Evidence-selected supervision and recovery |
| 4 | PHASE-0004 | accepted | PHASE-0003 | Cross-domain evidence from unchanged agent machinery |

## Benchmark contracts

| ID | Status | External authority | Product behavior measured |
| --- | --- | --- | --- |
| BENCH-0001 | accepted | Gymnasium, ARC-AGI-3, Hack The Box, and software-task evaluators | General task completion, efficiency, reliability, and recovery |

## Active experiments

None. Create an EXP document before changing an accepted algorithm on the
strength of an untested hypothesis.

## Active workstreams

| ID | Area | Current owner | Related phase |
| --- | --- | --- | --- |
| WORK-0001 | Vharness Next architecture and implementation | unassigned | PHASE-0001 |

## Blocked decisions

None.

## Inherited and historical material

These documents remain useful context but do not govern Vharness Next. This
classification implements the operator's explicit decision that AgentStorm
work must not impede the AVO-inspired redesign.

| Document | Classification | May govern implementation? |
| --- | --- | --- |
| `agentstorm.md` | Inherited proposal | No |
| `dynamic-safe-method-assessment.md` | Inherited phase plan | No |
| `plans.md` | Inherited roadmap | No |
| `transition.md` | Inherited transition notes | No |
| `tui-operator-console.md` | Inherited interface plan; source material for ADR-0004 | No |
| `workspace-project-foundation.md` | Inherited implementation plan | No |
| `todo` | Inherited task list | No |
| `decision-log.md` | Pre-Plant planning record | No |
| `worklog.md` | Pre-Plant planning record | No |
| `schematics/README.md` | Pre-Plant schematic instructions | No |
| `schematics/system-context.md` | Pre-Plant draft schematic | No |

## Protocol maintenance

The vendored `PROTOCOL.md`, `schema/metadata.schema.json`, and `templates/`
are a snapshot, not a dependency or submodule. Preview updates with
`/home/flub/plant/plant update plans --dry-run`, apply them only as an explicit
adoption change, and validate with `/home/flub/plant/plant check plans`.
