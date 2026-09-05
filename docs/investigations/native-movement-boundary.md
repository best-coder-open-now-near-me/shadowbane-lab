# Passive movement boundary investigation

This is an **unfinished-feature diagnostic**, disabled by default. It provides no
movement or camera actuation and does not make WASD/controller/drag available.
The integration owner reconciles startup/rollback and the combined package. Do not
install this branch's DLL independently or replace the shared client/VM.

## Question answered by this trace

For the reviewed client's native world-update virtual dispatch, which thread and
receiver execute it, and what native path-count/movement-state values are visible
there? Static inspection identifies the update and its native movement call. A
read-only guest memory check matched the entire normalized update digest and original
virtual slot, but cannot establish execution/thread identity. Existing diagnostic
artifacts contain no armed trace of this boundary.

The trace does **not** establish immediate stop, server acknowledgement, action-queue
cancellation, text-entry classification or complete collision-preserving steering.
Idle state alone cannot prove those behaviors. They remain movement-assignment work.

## Source and lifecycle

`movement_boundary_trace.cpp` validates the current reviewed executable fingerprint,
all 2350 bytes of the update method normalized over its 63 PE relocations, and the
original thunk before the existing atomic slot helper installs one passive callback.
Only the reviewed executable variant checked in this assignment is supported.
There is no search or fallback. Every call forwards the original receiver and double
argument and preserves its integer return. No engine functions other than that
original update are called; no actor, destination, camera or UI values are written.

Initialization follows process pinning and graphics executable verification, before
the shared renderer starts. An explicitly requested trace failure participates in
initialization rollback. With the opt-in unset, no mapping or slot change occurs.
The integration owner reconciles this additive wiring with newer shared lifecycle.
One lifecycle mutex serializes production/test admission and stop, and admission
compares the supplied creation FILETIME to GetProcessTimes for the current process.
A retained generation is never reset or restarted. Stop disables publication, drains the bounded publication section, and restores only
our own slot. The original function pointer, code and 18,480-byte mapping remain
process-pinned, including startup failure and late callback cases. There is no worker,
input sampler, command receiver or competing movement authority in this diagnostic.

The mapping name includes PID and creation FILETIME. Its header has magic `WBMVTR1`,
schema 1, record size 72, capacity 256 and exact identity. Each record commits its
sequence after its payload; the read-only collector accepts only identical committed
slots across two independent reads. Overwritten/missing sequence counts are retained
in output. Read failures are explicit; UI fields are named *candidates*, not gating
proof. Captures include process-local addresses and stay private under `artifacts/`.

## Reviewable procedure through the existing package workflow

1. The integration owner reconciles this source and runs both native profiles and
   their boundary/policy CTests, plus the Python collector tests. Package with the
   existing builder and record the combined SHA/package hash. This checkpoint does
   not authorize an early shared VM/client replacement.
2. If a narrowly scoped connected observation is authorized in that workflow, set
   `WONDERBANE_MOVEMENT_TRACE=1` **only in the intended client launch environment**.
   Do not set it globally. Unset it for all ordinary launches. Use the existing
   client lifecycle; do not attach a second DLL or inject a separate tracer.
3. After successful initialization, obtain that client's PID and process creation
   FILETIME from the existing verified identity. Run the installed Python module:

   ```powershell
   python -m shadowbane_lab.client_extension.movement_boundary `
     --process-id <verified-pid> --creation-filetime <verified-filetime> `
     --seconds 10 --output artifacts/movement-boundary-private.jsonl
   ```

   The output must not already exist. Run the collector in the same Windows session
   as the client. It opens the mapping read-only and performs no client input.
4. First capture idle world updates only. Check stable receiver, `read_valid=1`,
   monotonically increasing sequences and native delta, and compare observed thread
   to the exact foreground client's window thread. Retain disagreements as evidence;
   never enable actuation just because a method is named Update.
5. Request any further connected observation only for its remaining specific fact.
   A later queued-path/cancellation test needs an independently verified native stop
   implementation and appropriate bounded test; this trace is not that proof.

## Developer validation

Both Win32 DLL profiles build and all 22 CTests pass in each profile. Production tracing code is compiled into tests with
an isolated test-only installation seam and test original callback. Tests cover
opt-in absence, unsupported executable rejection, exact lifetime header, duplicate
start, committed publication, invalid receiver reads, unchanged call-through,
held original callback across shutdown, callback after shutdown, startup failure
after slot visibility, retained mapping/code responsibility and replacement-slot
protection, stale creation-time rejection and concurrent stop blocked behind a held
installation. The test seam is absent from production builds. These are lifecycle
regressions, not a substitute for observing the real client thread.

Python tests verify ABI sizes, exact-client rejection, two-read coherence, ring
wrap/overwrites, sequence regression, malformed size and nonfinite delta rejection.
