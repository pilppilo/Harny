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
