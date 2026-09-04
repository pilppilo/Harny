---
id: WORK-0001
title: Vharness Next architecture and implementation workstream
type: workstream
status: active
owners: []
created: 2026-09-04
updated: 2026-09-04
depends_on: []
supersedes: []
related: [ARCH-0001, ROAD-0001, BENCH-0001, PHASE-0001]
---

# Vharness Next architecture and implementation workstream

Append entries in chronological order. Do not rewrite prior observations.
Copy unresolved items forward until resolved or explicitly dropped.

## 2026-09-04 00:00 UTC — Planning session

- **Goal:** Establish an implementation-ready AVO-inspired redesign plan without
  making AgentStorm or inherited plans a prerequisite.
- **Work completed:** Adopted Plant v1.1 at revision `8a755e2`; accepted ARCH-0001,
  ADR-0001 through ADR-0004, ROAD-0001, and BENCH-0001; drafted four phases and
  SCHEM-0001; routed inherited plans as non-governing reference.
- **Evidence:** `/home/flub/plant/plant check plans` result to be recorded after
  the complete plan set is written; Git diff remains the review artifact.
- **Discoveries:** The existing product is a bounded probe/generator/detector/
  evaluator pipeline. The new kernel can be built alongside it without an
  AgentStorm-first refactor or immediate default-path change.
- **Open questions:** None blocks PHASE-0001. Exact PHASE-0004 suites and versions
  are intentionally frozen when that phase begins.
- **Suggested next action:** Validate the plan set, review the diff, then begin
  PHASE-0001 with baseline tests and contract implementation.

## 2026-09-04 20:41 UTC — Planning validation

- **Goal:** Validate the adopted snapshot and governed plan set.
- **Work completed:** Plant advanced during adoption; corrected snapshot
  provenance from the earlier observed `8a755e2` to actual source revision
  `712f419`, added its pinned lock, and refreshed the changed index template.
- **Evidence:** `/home/flub/plant/plant --json check plans` returned
  `{"errors": [], "ok": true}` before the provenance refresh; a final check
  follows this entry.
- **Discoveries:** Plant revision `712f419` adds the supported pinned snapshot
  and non-destructive update workflow; it does not change protocol version 1.1.
- **Open questions:** None.
- **Suggested next action:** Run final check, dry-run snapshot update, and Git
  whitespace/status review.

## 2026-09-04 20:44 UTC — Final plan-set validation

- **Goal:** Close planning validation with reproducible evidence.
- **Work completed:** Ran the Plant conformance checker, pinned-update preview,
  and Git whitespace/status checks from `/home/flub/vharness-next`.
- **Evidence:** Plant check returned `{"errors": [], "ok": true}`; update
  dry-run returned source revision `712f419` with `ok: true`; `git diff --check`
  returned no errors.
- **Discoveries:** The governed route is internally consistent and PHASE-0001 is
  ready. All inherited plans remain present but are explicitly non-governing.
- **Open questions:** None.
- **Suggested next action:** Review and commit the planning snapshot, then begin
  PHASE-0001 in a fresh implementation task using WORK-0001 for handoff notes.

## 2026-09-04 21:20 UTC — AVO paper alignment review

- **Goal:** Re-read the complete AVO paper, including equations and figures, and
  tighten the beginning phases before implementation.
- **Work completed:** Made multi-action attempts, externally accepted commits,
  and a single committed lineage foundational in PHASE-0001; gave the PHASE-0002
  agent explicit control over lineage, knowledge, action, debugging, and
  evaluation; moved supervisor threshold selection to a PHASE-0003 experiment;
  aligned the architecture, decision, roadmap, benchmark, index, and schematic.
- **Evidence:** Visually reviewed all 12 PDF pages, Figures 1-7, Table 1, and
  Equations 1-4. Plant check returned `{"errors": [], "ok": true}` and
  `git diff --check` returned no errors after the edits.
- **Discoveries:** Sections 3.1-3.3 define AVO as
  `Vary(P_t) = Agent(P_t, K, f)`: the agent controls a many-action variation
  step, unsuccessful work remains outside committed lineage, and the evaluated
  implementation is single-lineage. The paper does not publish context/memory
  algorithms or numeric supervisor triggers.
- **Open questions:** None blocks PHASE-0001. Plant has advanced beyond the
  pinned `712f419` snapshot; updating Plant is independent of these plan edits.
- **Suggested next action:** Re-run conformance checks and commit this focused
  plan tightening before PHASE-0001 implementation.
