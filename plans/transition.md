# Dynamic assessment transition

`workspace-project-foundation.md` is the prerequisite implementation contract
for local project/run organization. `dynamic-safe-method-assessment.md` is the
binding contract for the first dynamic-assessment milestone that follows it.
This document retains the durable principles and broader transition direction;
capabilities beyond those contracts remain future work.

Current state: Workspace v0 is implemented in commit `2b7e6e4`. The dynamic
assessment transition remains at its pre-HTTP foundation stage.

## Objective

Evolve vharness from a batch-oriented static-analysis harness into an
authorization-first, stateful assessment framework for lab and explicitly
scoped targets. The system will plan, validate, execute, observe, and record
small actions rather than allowing an LLM to issue unrestricted shell commands.

The existing SAST workflow remains supported throughout this transition.

## Operating principles

- Every tool action is typed, auditable, and bounded.
- Scope enforcement is implemented in code, not delegated to prompt text.
- The default posture is passive or low-impact observation.
- Higher-risk or state-changing actions require an explicit policy tier and
  operator approval.
- Findings are evidence-backed and distinct from unverified hypotheses.
- Sessions can be stopped and resumed without losing their action history.

## Architecture target

```text
planner -> typed action -> policy engine -> approved tool executor
   ^                                                   |
   +------- normalized observation <- evidence --------+
```

Persistent session state holds targets, assets, actions, observations,
hypotheses, findings, artifacts, budgets, and approvals.

## Phased plan

### 1. Foundations

- Define typed tool actions and normalized tool results.
- Add durable session, action-ledger, and observation persistence.
- Use action fingerprints to prevent repeated equivalent work.

### 2. Scope and policy control

- Add explicit hostname, URL, CIDR, port, and protocol allowlists.
- Canonicalize targets and validate redirects before any request.
- Enforce total-action, concurrency, rate, output-size, and time budgets.
- Classify tool actions by risk and add an approval interface.

### 3. Safe tool execution

- Define a tool plugin contract with schemas and capability metadata.
- Start with a scoped HTTP observation client.
- Run external tools through bounded subprocess workers, never LLM-produced
  shell strings.
- Capture normalized outputs and content-addressed evidence artifacts.

### 4. Agent loop

- Add structured planner output and validation.
- Implement observe -> decide -> policy -> execute -> record -> observe.
- Add termination rules for objectives, budgets, failures, and repeated work.
- Support checkpointing and session resumption.

### 5. Asset and finding workflow

- Build an asset graph for hosts, services, applications, and endpoints.
- Track hypotheses separately from validated findings.
- Require validation evidence before reporting a finding.
- Extend reports with session scope, policy decisions, and evidence links.

### 6. Controlled capability expansion

- Add low-impact discovery tools only after policy enforcement is integrated.
- Add higher-risk validation capabilities behind explicit policy tiers and
  operator approval, for authorized lab environments only.

## Implemented

- Local `SKILL.md` prompt support with bounded loading, provenance hashes, CLI
  selection, and run-log metadata.
- Typed `ToolAction` and `ToolResult` contracts in `src/vharness/tools.py`.
- Tool registry foundation, separate from LLM planning.
- SQLite-backed `AssessmentStore` in `src/vharness/assessment.py` for
  assessment sessions, action history, and observations.
- Deterministic action fingerprints for duplicate-action detection.
- Unit tests for the session store and action fingerprint behavior.

## Not yet implemented

- Network reconnaissance or interaction tools.
- Policy/scope enforcement and approval gates.
- An LLM-driven agent loop or function calling.
- Asset graph, evidence-artifact store, and finding validation workflow.
