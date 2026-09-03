# AgentStorm: extensible agent and tool runtime

> Future architecture exploration. This document does not define the Phase 1
> dynamic-assessment implementation; see `dynamic-safe-method-assessment.md`
> for that binding, single-planner milestone.

## Objective

Evolve Vharness into a general agent-and-tool runtime that supports agents and
subagents operating in Linux environments. The existing security-assessment
workflow remains a first-class use case, but it becomes a layer on top of a
generic runtime rather than defining every tool interaction.

## Repository boundary

### Vharness core

The core repository is the host runtime. It owns:

- Plugin discovery, compatibility checks, and lifecycle.
- Generic tool-call and tool-result contracts.
- Agent and subagent lifecycle, task assignment, and message routing.
- Shared task state, artifact references, trace IDs, and run history.
- Execution-backend interfaces for local Linux, containers, SSH, and VMs.
- Task profiles that assign capabilities to agents.
- Enforcement of resolved capability grants, target scope, resource limits, and
  child-agent authority attenuation.
- Logging, approval, and audit hooks.

Core must not accumulate a catalog of Linux commands, reconnaissance tools, or
agent personas.

### `vharness-plugins`

The plugin repository is the ecosystem of installable functionality used with
Vharness. It contains independently installable and versioned packages such
as:

```text
plugins/
  local-linux-backend/
  linux-shell/
  recon-tools/
  web-tools/
  agent-packs/
docs/
templates/
```

Plugins can contribute tools, agent providers, execution backends, task
profiles, policies, parsers, renderers, and lifecycle hooks. Discovery reads
declarative metadata only; selected plugin code is activated only after profile
resolution and validation. Neither discovery nor activation may perform an
assessment action.

## Runtime model

```text
Task profile
  -> selects installed plugins, tools, agents, and execution backends
  -> starts a parent agent
  -> parent may spawn subagents and assign task-specific capability sets
  -> agents issue typed tool calls
  -> selected backend executes the call and returns structured results
  -> results, artifacts, and messages are shared through task state
```

Subagents are ordinary agents with task-specific capability sets. They are not
permanently restricted to fixed roles: a task can give a worker shell, HTTP,
browser, filesystem, and artifact tools together, or grant all installed
capabilities to a trusted local worker.

## Profile-selected runtime

The default is profile-selected: installed functionality is available to be
chosen, but each task profile explicitly assigns initial capability grants,
plugins, tools, backends, and subagent-spawn capability to its agents. Core
enforces the resolved grants at every tool and delegation boundary.

An explicit `trusted-local` profile provides Pi-style full local capability
for trusted work. It must be deliberately selected, never inferred merely
because a plugin is installed.

```text
general-local
  tools: filesystem, shell, browser
  agents: general
  backend: local-linux

recon
  tools: dns, http, web, shell, artifacts
  agents: coordinator, worker
  backend: local-linux

trusted-local
  tools: "*"
  plugins: "*"
  agents: "*"
  backend: local-linux
  subagent_spawn: true
```

Policy plugins decide the initial grant and may narrow it further; core makes
the resulting grant, scope, budgets, and child-agent attenuation
non-bypassable. This is configurable runtime behavior, not a limitation on
which techniques a trusted plugin can provide.

## Core contracts

Generalize the existing assessment-specific action model into a generic call
contract:

```text
ToolCall
  call ID and idempotency key
  tool name
  JSON arguments
  principal/agent ID, task/session ID, and trace ID
  resolved capability grant and target scope
  execution workspace, deadline, and resource/output budgets
  execution context and metadata

ToolResult
  structured output
  stdout/stderr and artifact references
  status or structured error
  timing and execution metadata
```

Streaming output is emitted as append-only events followed by exactly one
terminal `ToolResult`. The idempotency key allows retried calls to be safely
recognized by the job supervisor.

Plugins register stable implementations of:

- `Tool`
- `AgentProvider`
- `ExecutionBackend`
- `TaskProfile`
- `Policy`
- Agent preset/role definitions and coordinator strategies
- Optional parsers, renderers, and lifecycle hooks

The runtime loads and composes these implementations. Security-assessment
concepts such as hypotheses, findings, and evidence validation remain in an
assessment package or task profile above the generic runtime. Scope and grants
are core-enforced execution inputs, although plugins may supply the decisions
that create them.

## Linux environments

The first backend is local Linux. It accepts structured process specifications:
executable, argument list, working directory, environment, and configured time
or output limits. It streams stdout/stderr and returns exit and timing data.

Plugins may expose a raw shell tool when a selected profile permits it, but
well-defined tools should use structured invocations rather than requiring an
agent to compose shell strings. The same backend interface later supports
containers, SSH hosts, and VMs.

## Implementation order

The detailed build phases below are authoritative. Their delivery order is:

1. Generic calls, immutable IDs, grants, streaming events, and terminal
   results.
2. Manifest-only discovery, profile resolution, and selected-plugin activation.
3. One installed tool through the core job supervisor and a local-Linux backend
   provider.
4. Parent-child lifecycle and an attenuated child grant.
5. Durable artifact, observation, and finding projections.
6. Recon, hardening, and additional execution/agent packs.

## First acceptance test

```text
Install core, a local-Linux backend provider, and one tool plugin
  -> resolve a profile before importing selected plugin code
  -> issue a grant-checked plugin tool call through the core supervisor
  -> backend executes it
  -> streaming events and one terminal result enter shared task state
  -> parent/child delegation is added only after this path is reliable
```

## Recon workbench architecture

AgentStorm is an offensive/defensive recon workbench, not a fixed general-chat
framework. Its architecture protects runtime coherence while retaining the
freedom to add techniques, tools, agents, and execution environments.

The governing rule is:

> Core owns invariants and enforcement. Plugins own behavior and policy
> decisions. Profiles choose composition and initial grants.

### Core invariants

Core remains intentionally small and provides the primitives that must be
consistent across every extension:

- Task, session, agent, parent-child, and trace identities.
- Shared state, event routing, task handoff, and resumable job history.
- Process/job lifecycle: start, stream, cancel, timeout, cleanup, and resume.
- Manifest discovery, profile resolution, selected-plugin activation,
  compatibility checks, and lifecycle bookkeeping.
- Content-addressed artifact storage and immutable provenance metadata.
- Generic capability, tool-call, result, and event contracts.
- Capability-grant, target-scope, budget, and child-authority enforcement.

Core does not prescribe reconnaissance methods, a permanent agent hierarchy,
or a single permission policy. Plugins may provide policy decisions and profile
definitions, but core validates and enforces their resolved grants at every
tool-call and delegation boundary.

### Plugin-owned capabilities

Plugins freely implement and register:

- Recon techniques: network, web, cloud, source-code, and local-host
  enumeration.
- Analysis techniques: fingerprinting, correlation, prioritization, reporting,
  and remediation generation.
- Tool integrations: command wrappers, protocol clients, parsers, wordlists,
  and data adapters.
- Execution-backend providers: local Linux, container, VM, SSH, or remote
  worker.
- Agent providers: local child process, container, SSH, or remote agent
  service.
- Agent presets/roles: scout, specialist, verifier, and hardening reviewer.
- Coordination strategies: fan-out/fan-in, breadth-first CTF, Linux-hardening
  audit, or any custom strategy.
- Policies and profiles: cautious authorized assessment, CTF breadth-first,
  local hardening, and trusted-local modes.

Plugins describe their components, settings schema, dependencies, compatible
core version, and lifecycle methods in a declarative manifest stored as wheel
metadata. Core reads these manifests without importing plugin code, resolves
the profile, then imports and activates only selected compatible plugins.
Activated plugins must not start jobs or contact targets until a task invokes a
registered capability.

### Composition model

Profiles select installed components for a task. They are configuration and
composition, not a permanent restriction on what a plugin is capable of.

```text
profile
  -> allowed/selected plugins and tools
  -> agent and subagent providers
  -> execution backend(s)
  -> policy implementation and resource settings
  -> artifact, state, and reporting configuration
```

`trusted-local` is an explicit profile that selects all installed capabilities
for trusted work, including raw shell and subagent spawning when installed.
Other profiles select a smaller compatible set. The runtime never infers
trusted access solely from installation.

Every delegation attenuates authority. A child receives no more than the
intersection of its parent grant, the selected profile grant, the specific
delegation request, and the policy decision:

```text
child grant = parent grant
              ∩ selected profile
              ∩ delegation request
              ∩ policy decision
```

### Evidence and state model

Do not treat every tool result as a finding. Persist three linked concepts:

```text
Artifact
  Immutable raw output: command stream, response, screenshot, file, or log.

Observation
  A normalized claim derived from an artifact. Includes target/context, method,
  tool and parser versions, timestamp, confidence, scope/context proof, and
  artifact references.

Finding event
  A higher-level conclusion event backed by one or more observations: proposed,
  corroborated, rejected, or reported.
```

The evidence graph is the handoff mechanism: scouts add observations,
specialists query relevant observations, and verifiers append corroboration or
rejection events without deleting or mutating raw evidence. Current finding
state is a projection of the append-only event history.

### Plugin lifecycle and isolation

Support a registry lifecycle that allows capabilities and temporary task
resources to be mounted and cleaned up:

```text
discover -> register -> configure -> task start -> execute/events
  -> task stop -> cleanup -> unregister
```

Use two plugin execution classes: in-process components for manifests,
schemas, parsers, renderers, and lightweight orchestration; isolated workers
for external commands, dependency-heavy integrations, and forcefully
cancellable operations. Do not depend on unloading Python modules in-process.
Code may remain loaded after unregistration; isolated process or container
workers provide true dependency separation, upgrade, and cancellation.

### Agent topology

Coordination is a replaceable plugin strategy. A high-value recon strategy is
fan-out/fan-in:

```text
target -> scout agents -> evidence graph -> specialist agents
       -> verifier -> report or next actions
```

Core owns agent identities, grants, state transitions, cancellation, and job
handles. Agent-provider plugins own execution transport; coordinator-strategy
plugins own delegation decisions; agent packs own prompts and role presets. A
coordinator may delegate based on observations, but it is not a permanent core
service. Alternative plugins can implement a single-agent workflow, manual
orchestration, CTF breadth-first work, or local hardening review.

## Build plan

### Phase A — Call, grant, and event primitives

1. Define immutable task, agent, parent-child, call, and trace IDs.
2. Introduce generic `ToolCall`, streaming `Event`, terminal `ToolResult`,
   capability-grant, target-scope, deadline, workspace, and budget models.
3. Add a minimal append-only event store and compatibility adapters for the
   current assessment action/result types.
4. Enforce call idempotency, grant checks, and resource limits in the core job
   supervisor.

**Exit condition:** a task can record a call and streaming events, produce one
terminal result, safely retry an idempotent call, and reconstruct that minimal
history after restart.

### Phase B — Manifest-only discovery and profiles

1. Define a versioned declarative plugin manifest embedded in package/wheel
   metadata and an explicit selected-plugin activation API.
2. Read manifests and validate compatibility without importing plugin modules.
3. Add registries for tools, agent providers, execution backends, profiles,
   policies, parsers, and reporters.
4. Resolve profiles to initial grants before activating selected compatible
   plugin code; include the explicit `trusted-local` profile.

**Exit condition:** the runtime can list installed capabilities and resolve a
profile without executing third-party plugin code; selected plugins activate
only after resolution succeeds.

### Phase C — First tool/backend vertical slice

1. Define the `ExecutionBackend` contract and a structured process request.
2. Implement the core job supervisor, which guarantees call lifecycle,
   streaming-event order, deadline, cancellation request, terminal result, and
   cleanup orchestration.
3. Build `local-linux-backend` as a provider plugin responsible for process
   transport and process-specific cleanup.
4. Complete one installed tool plugin through the selected local backend.

**Exit condition:** an installed plugin tool executes through
`local-linux-backend`, streams events, obeys its resolved grant/budget, and
returns exactly one terminal result without a core change.

### Phase D — Parent and child agent vertical slice

1. Define core agent handles, state transitions, delegation requests, and the
   child-grant attenuation rule.
2. Implement `subagent-local` as an agent-provider plugin that launches a
   child with task context, selected profile, grant, workspace, and event link.
3. Add one coordinator-strategy plugin and one role preset; keep provider,
   preset, and strategy as separate contracts.
4. Complete parent -> child -> plugin tool -> parent-result flow.

**Exit condition:** a parent can start, observe, cancel, and receive the final
result from a child, and the child cannot exercise authority outside its
attenuated grant.

### Phase E — Durable evidence projection

1. Add content-addressed artifact storage and artifact-reference events.
2. Add append-only observation and finding events with provenance links.
3. Build projections for assets, observations, and finding states while
   preserving raw artifacts and historical events.
4. Migrate the existing assessment store through compatibility adapters.

**Exit condition:** tools, scouts, and verifiers can independently append
evidence; restarting reconstructs the same projected asset and finding state
from immutable events.

### Phase F — Workbench packs and lifecycle expansion

Build these as separately versioned packages in the `vharness-plugins`
monorepo, extracting repositories only if their contracts and release cadence
diverge:

1. `linux-shell`: optional structured-command and raw-shell capabilities.
2. `asset-scout`: target intake plus DNS, HTTP/TLS, and service-fingerprinting
   observations.
3. `evidence`: parsers that normalize raw outputs into assets, URLs,
   technologies, services, and candidate findings.
4. Agent packs for scout, specialist, verifier, and hardening-reviewer presets
   plus fan-out/fan-in and breadth-first strategies.
5. `linux-hardening`: local inventory, baseline mapping, remediation planning,
   and verification tasks.
6. Additional web, source-code, cloud, container/VM/SSH, and reporting packs.
7. Hot lifecycle behavior only after ordinary task start/stop cleanup is
   reliable; use isolated workers where forceful cancellation is required.

**Exit condition:** the complete fan-out/fan-in demonstration runs with
installed plugins, append-only evidence, and no new core abstraction required
for a new technique or agent strategy.

## Initial end-to-end acceptance scenario

```text
Install Vharness plus local-linux-backend, asset-scout, evidence, and
subagent-local plugins
  -> select a recon profile
  -> create a task and target context
  -> coordinator launches parallel scout children
  -> scouts emit raw artifacts and normalized observations
  -> coordinator delegates relevant facts to specialist/verifier children
  -> verifier promotes or rejects candidate findings with linked evidence
  -> task report contains findings, observations, artifacts, lineage, and
     complete job history
```
