# Architecture schematics

This directory is the shared visual index for the `next` architecture. Keep
schematics concise, searchable, and synchronized with the decisions that
shape them.

## Schematics

- [System context](system-context.md) — major layers, responsibilities, and
  the unresolved enforcement boundary.

## Working conventions

- Prefer Mermaid diagrams in Markdown so agents and humans can search and
  revise them without a binary editor.
- Link each settled architectural change to an entry in
  [`../decision-log.md`](../decision-log.md).
- Mark unsettled choices as `Decision pending`; do not present them as
  established architecture.
- Append implementation discoveries to [`../worklog.md`](../worklog.md) and
  promote durable conclusions into a plan or decision entry.

