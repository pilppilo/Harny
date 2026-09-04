# System context

Status: initial schematic; enforcement boundary decision pending.

```mermaid
flowchart TB
    Operator[Operator / task owner]
    Benchmark[External benchmark and verification systems]

    subgraph VH[Vharness next — programmable agent system]
        Agent[Agent and supervisor]
        Memory[Persistent memory and candidate lineage]
        Feedback[Feedback interpretation and recovery]
        Tools[Tool interfaces and action proposals]
        Agent --> Memory
        Agent --> Tools
        Feedback --> Agent
        Memory --> Agent
    end

    subgraph RT[Execution runtime — exact ownership decision pending]
        Execution[Action execution]
        Identity[Identity and credentials]
        Enforcement[Policy and isolation enforcement]
        RuntimeLog[Runtime auditability]
    end

    Operator --> Agent
    Agent --> Tools
    Tools --> Execution
    Identity --> Execution
    Enforcement --> Execution
    Execution --> RuntimeLog
    Execution --> Feedback
    Benchmark --> Feedback
```

## Current agreement

- AVO concerns sustained capability: memory, execution feedback, recovery,
  supervision, and long-running progress.
- The agent and harness may propose actions.
- Existing external systems continue to own authorization, target lifecycle,
  benchmark verification, and other responsibilities assigned to them by the
  repository operating boundary.

## Decision pending

`plans/agentstorm.md` currently assigns enforcement responsibilities to
Vharness core, while the NVIDIA-informed model places authoritative identity,
policy, credentials, isolation, and auditability below the programmable
harness. Do not implement either placement as settled until the governing
direction is chosen and recorded in `plans/decision-log.md`.

