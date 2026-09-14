# Vendor manager host 0.3.4

Source: `1e804daafcf18cd16d967fdb3250d520058c592f`.
Feature branch: `codex/vendor-rolling`.
Integration destination: `codex/native-lifecycle-hardening`, followed by reviewed
`main`. This work remains unmerged.

## Delivered behavior

The test VM has a separate installed host 0.3.4 and vendor dashboard, attached to
the existing exact game client. The worker's health, dispatch permit and
vendor capability were verified through the authenticated status route.
The dashboard page is served correctly and its browser launch was requested.
The initial job queue is empty. No new crafting batch was started during this
installation; the running native 1.8.2 client was not changed or restarted.

The controls start one capacity batch, pause, resume and stop. The job detects
rank growth while filling and waits for the owned Inventory before Keep.
Unknown affixes are preserved. Native-confirmed receipts are persisted; partial
or uncertain actions require review rather than replay. Controls bind to both
the displayed job and exact client. A previous host worker cannot receive the
new operation without advertising its exact-lifetime capability.

## Package and validation

Final wheel SHA-256:
`f0596462a27b5ef12ae6ec3580b0ade4d00c80ff19e72dc971b0cdf0ece812de`.

The wheel was built from an exact-commit archive with embedded source identity.
Its archive integrity, installed version, source identity, module locations and
manager preflight were verified. Native source remains `8aad37f`.

The full host suite passed 2150 tests and 571 subtests. Fourteen explicit
environment skips cover symlink privilege and unbound native movement fixtures.
Ruff, dashboard JavaScript syntax and whitespace checks passed. The final CSS
layout correction passed the 20 dashboard tests and 39 subtests.

An earlier wheel from `c923d54` was replaced before starting the manager;
both exact-source package artifacts remain local for traceability. Detailed
runtime identities, private manager logs/token, captures and installation
receipts remain outside Git. The background launch wrapper later timed out,
but a separate authenticated read confirmed the live manager and worker healthy.

## Active todo

Qualify the first batch started through the installed manager controls. Open the
random Gilded Scepter recipe and use **Roll available slots**. When prompted,
open that vendor's Inventory. The previous three-item Create/Keep command-line
batch remains separately qualified.

Remaining: native recipe/inventory window opening, complete affix evidence and
low-tier identity coverage, inventory/resource capacity, and live discard
qualification. Recurring replacement batches and automatic disposal are disabled.
