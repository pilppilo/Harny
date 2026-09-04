---
id: ADR-0004
title: Make the human operator a durable first-class participant
type: decision
status: accepted
owners: []
created: 2026-09-04
updated: 2026-09-04
depends_on: []
supersedes: []
related: [ARCH-0001, ROAD-0001]
---

# Make the human operator a durable first-class participant

## Context

Vharness is autonomous over long stretches but is operated by a person who
monitors progress, converses with the agent, and changes direction. Treating
that person as an out-of-band console user would make steering ephemeral and
resume behavior ambiguous.

## Decision

Operator messages and controls are typed, durable session events. The operator
can observe, message, steer, pause, resume, stop, request a checkpoint, and
request external evaluation. Current operator direction is mandatory context.
The system records when that direction changes the plan and exposes enough
state to explain current activity.

## Consequences

Human interaction is built with the session kernel, not added after autonomy.
The agent need not request approval for every action; the external runtime
enforces what may execute. Conflicting or ambiguous steering is surfaced to
the operator instead of silently choosing an interpretation.

## Alternatives considered

A log-only dashboard was rejected because monitoring without durable steering
does not meet the product interaction model. Mandatory per-action human
approval was rejected because it prevents sustained autonomous progress and
duplicates the runtime boundary.

## Evidence and references

- Operator decision recorded in this planning session.

