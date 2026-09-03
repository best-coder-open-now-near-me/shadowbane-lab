# Read-only terrain material polling

`python -m shadowbane_lab.diagnostics.terrain_material_poll` records stable,
bounded snapshots of the reviewed custom-terrain shader's current source graph.
It replaces the rejected debugger-based material probe.

The collector opens only read/query access to one exact PID and creation time.
It verifies the executable, sibling extension, repaired terrain instructions,
terrain draw entry, and global shader vtable before and after polling. It never
attaches a debugger, suspends a thread, changes a debug register, writes process
memory, invokes a client function, scans memory, performs GPU readback, or injects
input. By default it reads no pixels or texture bytes.

Each candidate is accepted only when the shader, owner, source, vector entries,
texture objects, and backing objects remain byte-identical across the bounded
read. At most 20,000 polls and 64 unique source graphs are retained. Inconsistent
concurrent reads are discarded and summarized rather than guessed.
Unknown texture vtables are retained only as unattributed class/address records;
their token and backing layouts are not interpreted. Polling is not an atomic
frame snapshot: it can miss sources and cannot exclude every ABA mutation.

Example for an already verified 1.6.13 client:

```powershell
python -m shadowbane_lab.diagnostics.terrain_material_poll `
  --pid 1234 `
  --creation-filetime 134329293478567243 `
  --output "$env:LOCALAPPDATA\ShadowbaneLab\client-extension\terrain-material.json" `
  --duration 5
```

The output maps runtime GL bindings to the reviewed in-memory tokens for base
textures, color layers, source alpha masks, and GPU-facing mask copies. Generated
or unattributed zero tokens remain labeled as such. The result does not identify
a screen pixel or authorize a cache edit.

## Optional resident alpha evidence

Add `--include-resident-alpha` to capture already-resident CPU bytes for source
alpha masks and the CPU backings of GPU-facing mask copies. It never reads color
texture bytes, calls an accessor, triggers lazy decoding, or reads GPU storage.
A missing pixel pointer is reported as `not_resident`, not repaired.

This option additionally verifies the exact reviewed pixel-accessor signature
before and after capture and requires the ArcImage backing vtable. Only square
64x64 or 128x128, one-channel GL_ALPHA / GL_TEXTURE_2D masks are accepted. Each
buffer is read twice and must agree; the existing complete ownership/header
checks still apply. Unknown classes/layouts are labeled without dereferencing
their pixel pointer. Alpha-read reservations, including failed and discarded
samples and both consistency reads, are capped at 16 MiB across the entire run.
Once exhausted, later metadata can still be captured with a budget-exhausted
label. This may yield few or no mask samples in a busy scene.

Schema 2 and later include raw-memory-order base64 bytes, dimensions, and SHA-256 per
accepted resident mask. These can be compared offline without another game
capture. Raw row/column axes are not established screen/world directions.
Matching source/copy hashes prove agreement of those CPU observations only;
they do not prove the GPU received matching bytes or that an upload occurred.

## Optional terrain geometry

Schema 3 adds `--include-mesh`, independently or together with resident alpha.
It accepts only the reviewed ArcSinglePolyMesh -> ArcMesh -> RenderNormal
triangle path. Cached draws and other classes/topologies remain explicitly
unattributed. Four exact layout signatures are checked before and after capture.
The already-reviewed source mask rotation is also recorded in degrees.

Positions (three float32 components), UVs (two float32 components), and uint16
triangle indices are retained losslessly as base64 plus hashes and bounds.
Vectors, finite coordinates, matching attribute counts, index ranges, and
repeated wrapper/header/action/buffer reads are checked. Limits are 4,096
vertices, 24,576 indices, and a separate 16-MiB buffer-read reservation budget
covering both reads and discarded attempts. Mesh contents participate in snapshot
deduplication, so a changed mesh cannot disappear behind identical material data.

These are resident source arrays, not a measurement of current GL array bindings
or proof of screen projection. The exact reviewed draw requests flags `0x1b`:
both color and mask use the same two-component UV vector before their different
texture matrices. Do not apply this interpretation to an unreviewed draw path.

## Explicit staged ownership mode

Schema 4 adds optional `--staged-ownership`. The default still requires the same
shader/owner contents at both ends of the entire graph read. That strong timing
condition can bias long geometry captures toward only the smallest terrain meshes.

Staged mode instead brackets the root association first, with an additional exact
ArcTerrainRenderObject vtable gate and source/wrapper header anchors. It then
double-checks the independently read material/mesh graph and requires those same
source/wrapper anchors at completion. The renderer may have advanced to another
draw meanwhile. Output labels this `staged-root-and-graph`; it never claims the
root is still current, that object lifetimes were pinned, or that an atomic frame
was captured. Concurrent ABA changes remain possible, as in default mode. This
is an explicit evidence-contract choice, not silently relaxed default validation.
