---
id: ADR-0003
title: Use environment contracts instead of behavioral profiles
type: decision
status: accepted
owners: []
created: 2026-09-04
updated: 2026-09-04
depends_on: []
supersedes: []
related: [ARCH-0001, BENCH-0001]
---

# Use environment contracts instead of behavioral profiles

## Context

Gymnasium, ARC-AGI-3, Hack The Box, and software tasks expose different data
and action surfaces. That mechanical difference does not justify separate
agent personalities, policies, memory algorithms, or control loops. The
product as a whole must be good at all of them.

## Decision

Each integration will describe its task, observations, legal action schema,
receipt schema, and external evaluation channel through one environment
contract. The same agent configuration and algorithms will interpret those
contracts. Environment names may select mechanical adapters, never hidden
behavioral prompts or benchmark-specific reasoning code.

## Consequences

Cross-domain evaluation can distinguish architectural progress from adapter
specialization. Domain knowledge may enter through task observations, tools,
and durable memory just as it would in real use; it must not be hard-coded as
a benchmark switch.

## Alternatives considered

Profiles such as `arc`, `gym`, and `htb` were rejected. They simplify early
demos but obscure whether one coherent system learned to use each environment.

## Evidence and references

- ADR-0001 and the operator's explicit whole-product requirement.

