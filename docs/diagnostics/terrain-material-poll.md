# Read-only terrain material polling

`python -m shadowbane_lab.diagnostics.terrain_material_poll` records stable,
bounded snapshots of the reviewed custom-terrain shader's current source graph.
It replaces the rejected debugger-based material probe.

The collector opens only read/query access to one exact PID and creation time.
It verifies the executable, sibling extension, repaired terrain instructions,
terrain draw entry, and global shader vtable before and after polling. It never
attaches a debugger, suspends a thread, changes a debug register, writes process
memory, invokes a client function, reads pixels/texture bytes, scans memory, or
injects input.

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
