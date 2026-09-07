# In-Memory Edit Graphs

## Goal

Extend in-memory composition from a linear sequence into a directed acyclic
graph of edits. A graph may branch one result into several independent edits
and may combine several edited results in a later edit. For example, two edits
of the original session may be separate logical branches and a third edit may
mix their outputs.

Every intermediate remains a `float32` NumPy array or array view. Only the
declared result is encoded and written as a new session.

This plan covers the graph work that remains. Materialized source loading, the
complete-array renderer, linear in-memory composition, materialized
autocalibration, final-only session output, and basic memory reporting already
exist and are not repeated here.

## Graph Semantics

A composition is a graph of named edit nodes:

```text
                         -> vocal cleanup --\
original session arrays                         -> mix -> final encoder
                         -> room processing --/
```

Each node has a stable ID, one edit command, one or more input node IDs, and
that command's ordinary edit options.

The reserved node ID `root` denotes the original input session. An edit node
may consume `root`, another edit node, or several edit nodes. A node with
several inputs sees one virtual session containing the tracks produced by all
of them.

The composition declares exactly one `result`. A non-empty graph writes that
node's outputs as the final session. Every other node must be an ancestor of
the result; reject disconnected work rather than evaluating and discarding it.
A graph with no edits has `result = "root"` and retains the existing identity
behavior without creating a destination.

Dependencies, not declaration order, determine execution order. Reject:

- duplicate or reserved edit IDs;
- unknown input IDs;
- direct or indirect cycles;
- an edit that depends on itself;
- `result = "root"` when edit nodes are present;
- nodes that cannot reach the result;
- explicit encoding options on any node except the result.

## Composition Format

Replace the implicit linear `[[edits]]` sequence with an explicit graph schema.
This is an incompatible representation and therefore uses schema version 2;
do not keep both implicit and explicit dependency semantics in the same
schema.

```toml
schema_version = 2
kind = "composition"
result = "master"

[[edits]]
id = "vocals"
command = "clip"
inputs = ["root"]
channel = ["x18:voice"]

[[edits]]
id = "room"
command = "clip"
inputs = ["root"]
channel = ["x18:room"]

[[edits]]
id = "master"
command = "mix"
inputs = ["vocals", "room"]
channel = ["vocals:*", "room:*"]
format = "flac"
subtype = "pcm_24"
```

Canonical `edit.toml` stores nodes in deterministic topological order, using
the node ID as the secondary ordering key when several nodes are ready. It
stores each resolved command and generated edit beside its node rather than in
positionally matched lists. This prevents reordering from changing the
association between a node, its recipe, and its resolved edit.

Suggested persisted shape:

```toml
[[edits]]
id = "vocals"
command = "clip"
inputs = ["root"]

[edits.resolved]
# Flattened command recipe.

[edits.edit]
# Complete generated edit with intermediate encoding fields omitted.
```

Validate the exact nesting with `tomlkit` before implementation so generated
TOML remains readable. The canonical form must not depend on command discovery
when replayed.

## Virtual Input Sessions

Give each graph node a `MaterializedSession` result. A one-input edit receives
that session directly. For a multi-input edit, construct a read-only virtual
session inventory without copying sample arrays.

Tracks from an upstream node use that node ID as their source name and retain
their output track name. Selectors therefore use `NODE:TRACK`, and
`NODE:*` selects every compatible track from that node. In the example, the
`master` mix receives tracks under the `vocals` and `room` source names.

This namespace prevents collisions when two branches both produce an output
named `main`. Preserve stream IDs and source provenance separately from the
selector-facing node namespace.

Do not implicitly include the original session or a sibling branch. A node
receives exactly the sessions listed in `inputs`. A node that needs both an
edited branch and untouched original tracks lists both the branch ID and
`root`.

The merged inventory is a logical view only. It must not concatenate arrays,
change timelines, or fill omitted media. Existing edit-class behavior remains:
an audio edit consumes audio tracks and omits media types it does not support.

## Graph Compilation

Compile the complete graph before loading audio or creating the destination:

1. Parse and validate node identities and dependency edges.
2. Resolve and flatten every command recipe.
3. Topologically order the nodes deterministically.
4. Build each node's virtual input inventory from predecessor output
   descriptors.
5. Generate and validate every node's logical edit.
6. Determine output identities, channel widths, frame extents, and sample
   rates.
7. Reject unsupported media, operations, selectors, and non-result encoding.
8. Calculate array consumers and a conservative peak-memory estimate.

Some analysis edits, including autocalibration, cannot know their exact output
ranges before reading samples. Represent their compile-time outputs
conservatively and replace them with resolved ranges during execution. Record
the resolved analysis values in the canonical node.

Compilation must not rely on list order beyond deterministic tie-breaking. A
node may be declared before its dependencies.

## Execution And Parallelism

Execute nodes in deterministic topological order. Logical branches are
parallel in the graph even if the first implementation evaluates ready nodes
one at a time. This supports fan-out and fan-in, including a mix whose inputs
are two independently edited branches.

Maintain a consumer count for every materialized node result:

- source arrays and branch outputs are read-only while shared;
- a node may use a view without copying when its operation permits;
- an operation may mutate in place only when it has the sole remaining owner;
- retain an array base until every dependent view has been consumed;
- release a node result immediately after its final consumer completes.

The shared `SourceMaterializer` remains graph-wide so two branches selecting
the same recorded source decode it once. Branch-local mutations must never
alter that cached source or a sibling branch.

Keep ready-node boundaries explicit enough for later concurrent execution, but
do not add threads or processes initially. Concurrent execution would need a
memory reservation for all simultaneously running nodes, deterministic failure
selection, cancellation, and control over native NumPy thread pools. It is a
later optimization, not required for graph semantics.

## Memory Planning

Replace the current linear stage estimate with graph liveness accounting. The
estimate must include:

- each distinct decoded source array;
- every predecessor retained across a fan-out;
- simultaneous inputs retained for a fan-in;
- each node's track, bus, route, concatenation, scaling, and analysis arrays;
- copies required because arrays have sibling consumers;
- final result arrays retained for encoding.

Count storage by base-array identity so views do not add bytes, while extending
the lifetime of their base. Simulate the deterministic execution order and
report the maximum live storage after every allocation and release.

For each node, retain both its output storage and the renderer's temporary peak.
The graph peak is the maximum of current live graph storage plus that node's
temporary requirement. Autocalibration uses the complete selected extent as a
conservative estimate until its retained ranges are known.

Do not add a fixed memory limit or a disk-backed fallback. On `MemoryError`,
report the planned peak and the allocation that failed, then release all graph
references.

## Final Output And Provenance

Only the result node may specify output paths, format, and subtype. Once every
ancestor has completed successfully, write one destination containing:

```text
edit.toml
session-record.jsonl
audio/
  ...
```

The canonical composition records:

- the original session record;
- every node ID and dependency edge;
- every flattened command recipe;
- every resolved generated edit;
- resolved analysis values;
- the result node and its encoding policy.

Intermediate nodes have no paths or encoding claims. The session record points
to the root `edit.toml` and contains file events only for result-node media.
Execution facts such as measured peak memory belong in `edit_started`, not in
the declarative graph.

If result encoding fails, retain the existing truthful partial-session
behavior. Failures before encoding must not create the destination.

## Dry Run

Update composition dry-run output to describe the graph rather than a numbered
linear sequence. Report:

- the original input record and result node;
- every node's command, dependencies, selected inputs, and logical outputs;
- deterministic execution order;
- frame extents, observed ranges where known, channel widths, and sample rates;
- arrays shared between branches;
- per-node output storage and temporary peak;
- releases after final consumers and estimated graph peak;
- resolved autocalibration values when analysis is required;
- final format, subtype, paths, and duration;
- confirmation that no intermediate media will be written.

Dry run may load arrays required for analysis but writes no destination and
releases all arrays before returning.

## Implementation Order

1. Replace the composition schema with stable node IDs, explicit `inputs`, one
   `result`, and node-local resolved command and edit data.
2. Add graph validation and deterministic topological ordering.
3. Namespace materialized track inventories by predecessor node and merge
   multi-input inventories without copying arrays.
4. Compile every node before materialization, including conservative analysis
   descriptors and result-only encoding validation.
5. Add graph-wide consumer counts, base-array liveness, and peak-memory
   planning.
6. Execute fan-out and fan-in nodes over the existing array renderer and
   materialized autocalibration path.
7. Write canonical graph provenance and encode only the declared result node.
8. Replace linear dry-run reporting with dependency, sharing, liveness, and
   graph-memory reporting.
9. Run the complete automated verification sequence.

Keep each implementation commit independently passing.

## Tests

Use 48 kHz WAV fixtures at least one second long for audio tests.

1. Parse, canonicalize, and replay a graph without command discovery.
2. Reject duplicate, reserved, unknown, cyclic, disconnected, and invalid
   result nodes before loading audio.
3. Execute nodes correctly when their declaration order differs from their
   topological order.
4. Fan one source into two edits and mix those two results in a third edit,
   comparing exact samples with the equivalent standalone operations.
5. Merge predecessor inventories without copying arrays and resolve
   `NODE:TRACK` selectors without collisions.
6. Decode a recorded source once when several branches consume it.
7. Prove that one branch cannot mutate a source or output observed by another
   branch.
8. Retain a shared result until its final consumer, then release its base array.
9. Verify measured peak storage does not exceed the graph estimate for fan-out
   and fan-in cases.
10. Run autocalibration in one branch and consume its resolved materialized
    output in a later fan-in node.
11. Preserve gaps, timelines, channel layouts, stream provenance, and stable
    selector identities through branches.
12. Reject encoding options on every non-result node before creating the
    destination.
13. Verify canonical `edit.toml` contains the full graph and no intermediate
    paths or encoding claims.
14. Verify the final session record contains only result-node media.
15. Verify graph dry run reports dependencies, sharing, releases, and peak
    memory while writing nothing.
16. Inject compile, allocation, analysis, and final-write failures and verify
    cleanup and truthful destination state.
17. Verify the zero-node identity graph creates no destination.

## Acceptance Criteria

- Compositions support arbitrary acyclic fan-out and fan-in, not only a linear
  previous-stage chain.
- A mix or other edit can consume the materialized results of two or more
  predecessor edits.
- Node IDs provide stable, unambiguous selectors and provenance.
- Every command and graph edge is resolved before source audio is loaded.
- Shared recorded sources are decoded once and cannot be mutated by a branch.
- Consumer-based liveness releases arrays after their final graph use.
- Dry run reports a conservative graph-wide peak-memory estimate.
- Only the declared result node is encoded or represented by file events.
- Canonical TOML completely describes and can replay the graph without command
  discovery.

## Additional work beyond the prompt

None.
