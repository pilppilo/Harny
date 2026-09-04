---
id: ADR-0001
title: Build one AVO-inspired domain-neutral agent core
type: decision
status: accepted
owners: []
created: 2026-09-04
updated: 2026-09-04
depends_on: []
supersedes: []
related: [ARCH-0001, ROAD-0001, BENCH-0001]
---

# Build one AVO-inspired domain-neutral agent core

## Context

Vharness must sustain progress across authorized assessment, interactive
reasoning, control, and software tasks. A frontier model alone does not
provide durable state, disciplined tool use, recovery, or long-horizon
progress. NVIDIA's Agentic Variation Operators work demonstrates a reusable
agent architecture whose core transfers while environment tools and
evaluation change.

## Decision

Vharness Next will use AVO as architectural inspiration, not attempt a
line-for-line reproduction. One general agent kernel will own the durable
reasoning loop, memory, context construction, feedback interpretation,
supervision, recovery, attempt history, and a single lineage of externally
accepted states. Within an attempt the agent controls when to consult prior
commits and knowledge, act, debug, and evaluate. Environments provide typed
observations, action descriptions, execution receipts, state references, and
evaluation receipts without changing that kernel.

## Consequences

The implementation must isolate environment mechanics from agent policy and
prove transfer with the same core. A benchmark-specific shortcut cannot enter
the core merely because it improves one score. AVO terminology may be used
where it clarifies provenance, but local names and contracts are authoritative.

## Alternatives considered

A benchmark-specific agent family was rejected because it would measure
specialization rather than general capability. Reworking AgentStorm first was
rejected because it would make inherited orchestration assumptions a gate on
the redesign.

## Evidence and references

- NVIDIA AVO paper: <https://arxiv.org/html/2603.24517v1>
- NVIDIA AVO overview: <https://developer.nvidia.com/blog/nvidia-avo-reaches-100-on-arc-agi-3-demonstrating-a-frontier-level-general-purpose-architecture-for-long-horizon-autonomous-agents/>
