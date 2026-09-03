# Terrain edge-copy branch-hit diagnostic

This collector answers one deliberately narrow question: does the running
1.6.13 client execute any of the four matching-material edge-copy completion
branches repaired by terrain_mask_refresh?

It is not a general terrain tracer and it does not attribute a screen pixel,
texture archive record, or terrain direction. The four routines are reported
as edge_0 through edge_3 because their world-direction labels have not been
proved.

## Safety and identity boundary

The collector fails closed unless all of the following match:

- the exact PID and process creation FILETIME supplied by the caller;
- the reviewed patched executable SHA-256;
- the reviewed 1.6.13 sibling extension DLL SHA-256;
- all four repaired instructions at their exact ASLR-adjusted RVAs; and
- the 32-bit image layout.

It uses the existing Win32 debugger transport and four hardware execution
breakpoints. It does not write client code or data, scan memory, read pixels,
read texture bytes, invoke client functions, or inject game input. A role is
disabled on the thread that hits it, and only the first observation per role is
retained. The entire run is bounded to 30 seconds and 128 hit events.

At a hit, the tool reads only the 430-byte terrain source object already held
in EBX. It records the three reviewed vector bounds, the base reference,
direction-completion byte, and dirty byte. Vector elements and texture objects
are not dereferenced.

## Invocation

Run inside the client VM with its local Python environment and an output path
on a local fixed drive:

    python -m shadowbane_lab.diagnostics.terrain_branch_hits
      --pid <exact-pid>
      --creation-filetime <exact-filetime>
      --output <new-json-path>
      --timeout 15

The output path is create-only. A stationary zero-hit result is valid evidence
that these branches were inactive during that interval, but it is not enough
to rule them out during terrain arrival. If stationary capture has zero hits,
repeat once while crossing the visible boundary and record input mode as
operator-keyboard.

Interpretation:

- A hit proves that the repaired matching-material completion branch executed.
- A zero-hit stationary capture calls for one bounded movement capture.
- Zero hits during both intervals means this visible seam was not produced by
  the repaired branches during the observed runs.
- Hits with unchanged appearance mean the repaired dirty-flag lifecycle was
  real but is not sufficient to remove this visual boundary.

Do not turn this into per-frame or per-draw tracing.
