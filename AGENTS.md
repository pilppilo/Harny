# Operating boundary

Vharness is used only after the operator has established authorization.

Do not add, propose, or require Vharness-side authorization verification,
benchmark-side policy gates, target lifecycle control, side-effect auditing,
or duplicate grading systems.

Develop Vharness for capable, efficient authorized recon and assessment,
including personal labs, CTFs, and enterprise engagements.

Existing external systems own authorization, target lifecycle, and benchmark
verification. Vharness benchmarks measure product capability, efficiency, and
quality using those systems; they do not recreate them.

Safe-method behavior is an initial capability/profile for development and
testing, not a permanent product limitation or universal architecture rule.

## Product-direction interpretation

The repository may contain narrow phase specifications, broad roadmaps, and
historical proposals. A phase-specific limitation is not a statement of the
product's permanent capability boundary unless the user explicitly says so.

Vharness is intended to become a capable, efficient authorized recon and
assessment tool for personal labs, CTFs, and enterprise engagements.
Authorization is an operator precondition, not a product-design constraint to
reinterpret or expand.

Do not infer, impose, recommend, or announce future product limitations from a
Phase 1 plan, benchmark plan, or safety-oriented development slice.

When plans appear to conflict, report the exact conflicting text and ask the
user which document governs. Do not independently declare a plan obsolete,
non-binding, incompatible, complete, or out of scope.

Do not edit plan/spec status, completion criteria, roadmap direction, or
architecture boundaries unless the user explicitly asks for that edit.

## Benchmark boundary

Benchmark work measures Vharness capability and efficiency. Existing external
systems already own authorization, target operation, lifecycle, auditing, and
verification.

Do not design, add, propose, or require replacement/adaptor systems for those
external responsibilities. Do not interpret a benchmark scenario as a product
capability restriction.

## Planning protocol

For Vharness Next planning and implementation, start at `plans/README.md` and
read its **Current focus** documents. Follow `plans/PROTOCOL.md`; do not treat
unindexed or inherited plans as governing direction. After changing plans, run
`/home/flub/plant/plant check plans` from the repository root. Plant is a
separate project; preview vendored updates with
`/home/flub/plant/plant update plans --dry-run` and apply them only through an
explicit adoption change that records the source revision.

# AGENTS.md — Python Engineering Standards

Apply these rules when creating or materially changing Python code. User
instructions and established repository conventions take precedence.

## Design first

Before implementing a non-trivial change:


Before implementing a non-trivial change:

1. Inspect nearby code, tests, and project configuration.
2. Identify whether the relevant area is already structured around clear module
   boundaries, or is an accumulation of script-style orchestration.
3. If it is script-style, improve the architecture as part of the change when
   doing so is small, local, and makes the changed behavior easier to test and
   maintain. Separate orchestration, I/O, parsing, and domain logic.
4. Do not preserve poor structure merely because it already exists. Do not
   perform an unrelated repository-wide rewrite.
5. Reuse established patterns where they are sound; otherwise introduce the
   smallest clear structure that the surrounding code can adopt.
6. State any material assumption briefly, then proceed.
7. Prefer the smallest design that cleanly meets the requirement.

Write production code, not one-off scripts. Keep orchestration separate from
domain logic, I/O, and parsing. A CLI entry point or `__main__` block may only
parse arguments, configure dependencies, and call an application function.

## Structure

- Give each module and function a clear, cohesive responsibility.
- Split code when responsibilities differ; do not split merely to meet a line
  count. Functions should normally be short enough to understand at a glance.
- Keep related behavior together. Do not create generic `utils.py` modules.
- Put new code beside equivalent existing code.
- Extract duplication when it represents shared behavior or policy; do not
  abstract coincidental similarity.
- Prefer explicit dependencies passed through constructors or parameters over
  global mutable state.
- Use guard clauses to keep nesting shallow.

## Types and data

- Add complete type hints to new or changed public APIs and important internal
  boundaries, including return types.
- Use domain models (`dataclass`, `TypedDict`, or an existing validation model)
  when data crosses a module, I/O, or business-logic boundary.
- Do not use `Any` unless required by an external API; explain the reason in a
  concise comment.
- Represent optional values explicitly with `T | None`.

## Errors and boundaries

- Validate untrusted input at the boundary: CLI arguments, HTTP requests,
  environment variables, files, and external API responses.
- Catch only errors that can be handled meaningfully.
- Preserve causes when translating errors: `raise DomainError(...) from exc`.
- Use project-specific exception types when callers need to distinguish a
  domain failure. Do not create custom exceptions for every error.
- Never use bare `except` or silently ignore an error.

## Readability and conventions

- Match the repository's formatter, linter, import style, Python version, and
  docstring convention. If none exists, use standard PEP 8 and a line length
  of 88.
- Use descriptive names. Introduce constants for values with domain meaning or
  values reused across the codebase; keep obvious local literals inline.
- Do not add unused imports, dead code, commented-out code, speculative
  abstractions, or compatibility layers that the task does not require.
- Use f-strings for interpolating values in new code unless the surrounding
  code or API requires another formatting style.
- Document public interfaces and non-obvious decisions; avoid docstrings that
  merely restate the function name or type signature.

## Verification

- Add or update tests for behavior changes and bug fixes when the repository
  has an appropriate test setup.
- Run the narrowest relevant formatter, linter, type checker, and tests.
- Report what was verified and any validation not run.

## Completion

Do not present incomplete, untested, or assumed behavior as complete. Clearly
state limitations, assumptions, and remaining work.