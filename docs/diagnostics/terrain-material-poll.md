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

Schema 2 includes raw-memory-order base64 bytes, dimensions, and SHA-256 per
accepted resident mask. These can be compared offline without another game
capture. Raw row/column axes are not established screen/world directions.
Matching source/copy hashes prove agreement of those CPU observations only;
they do not prove the GPU received matching bytes or that an upload occurred.
