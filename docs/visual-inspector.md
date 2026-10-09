# Selected-object Visual Inspector

In Graphics Lab, open **Visuals**, choose **Selected object** (or **My character**),
select the object in game, and press **Capture**. Choose the same client's cache
folder if it is not detected. Expand the render tree and select a row to see
attachment bone, meshes, texture layers, specular reference, template children,
and candidate object/equipment names. Save snapshot exports a local JSON report.
Captures are frozen and labeled; press Capture after changing selection or gear.

The native channel is `Local\WonderBaneVisuals-<pid>-<creation-filetime>`, schema 1.
It collects only on demand at the existing reviewed scene boundary, with no game
memory writes or new hooks. It verifies the selection before/after capture and
compares two bounded render-tree reads. Unsupported layouts, unreadable nodes,
cycles, repeated nodes, identity changes and more than 128 nodes produce an empty
failure snapshot. The channel rejects mismatched process lifetimes and publishes
through a sequence lock. The panel serializes requests across panel instances.

Runtime render IDs do not establish resource groups. All matching cache entries
remain visible, including ambiguous groups. CObject primary-render matches are
candidate names, not verified equipped item identities or slots. Template texture
references are not evidence of live material overrides. Unknown records remain
explicit errors; no item stats or attached effects are inferred. Selected scenery,
including doors, works only when its object and render tree satisfy the existing
reviewed binding; arbitrary world picking is not implemented.

Cache enrichment runs off the UI thread and checks file size/mtime across reading.
It is read-only, reports missing/duplicate dependencies and unsupported records,
and retains chosen-cache provenance. Exports never include raw client assets and
remain local unless explicitly shared.

Validation: full native build, 240 required native tests (three private-image
entries skip without explicit inputs), 5,250 host tests with 38 skips, and lint.
Seventeen inspector tests include actual Tk tree/details/export/disconnect behavior;
Win32 snapshot bytes were separately decoded by the Python host. The private
Archon render resolves to its known RHELD attachment, mesh and texture. Live VM
installation and selected-object acceptance are the active next steps.

This branch depends on katana PR #106 and targets main after that integration.
Install its full native DLL and these host modules together: graphics_lab/app.py,
katana.py, visual_inspector.py, visual_panel.py and world_data/object_navigation.py.
Retain exact source/hash receipts and follow deployment-policy.md; no retained
rollback binaries. Bot host/base upgrades remain independent of this cosmetic
and diagnostic overlay.
