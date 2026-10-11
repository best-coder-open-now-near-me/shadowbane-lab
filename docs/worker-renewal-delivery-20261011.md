# Worker renewal delivery - October 11, 2026

Host 0.3.102 is merged, qualified, installed and activation-verified. Native
1.8.65 and client resources remain unchanged by this host-only update. A fresh
client launch is verified and obsolete local and guest .101 software is retired.
Fresh login/group readiness and live `/come` arrival acceptance remain pending.

## Source and qualification

PR [#164](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/164)
merged as `7198d2d2dee29c4878f36fb7f9cdd81e1c172974` after all 15 hosted checks
passed at `0182bcc2b26ae9ce790a10a225a2a052845486e6`.
The graphics-preserving release is
`c89941f2ecc94a4da82c3e8ddd379bbcfd593474`.
The implementation separates bounded current authority and native renewal from
historical reconciliation/status writes. Original permit expiry, durable
Stop/Cancel recovery, Resume ordering, exact identity and cleanup ownership are
preserved. See [the source boundary](worker-native-maintenance.md).

The final full host suite passed **6,303 tests with 44 optional skips** on the
clean exact release. All 16 recorded package stages passed. Both native-fixture
profiles passed 76 movement, 86 combat and 245 actor IPC tests each, with no
failures/errors/skips. Six installed desktop cases and one real worker handshake
also passed without skips. All 491 source/wheel/installed modules match.
Independent package review passed; native source and runtime build inputs match
the qualified .65 release. Existing non-gating graphics findings are unchanged.

The preceding full-suite attempt at `b8463ec1` found seven stale test fixtures.
The test-only follow-up `0182bcc2` supplies the bounded authority API and explicit
observation boundary while retaining requested/interrupted/cleanup assertions.
All 53 affected tests passed, including independent review of the seven failures.
The failed run remains diagnostic evidence, not package qualification.

Private evidence lives under `artifacts/bot-deploy/20261011-host102/`:

| Evidence | SHA-256 |
| --- | --- |
| `package/host-qualification.json` | `7f32fc3e0be00f5a88688e1be543391059943441bd849b7b50a7852dfd4cc8f8` |
| Host .102 wheel | `dbc62ee9d298056de38b3b3714afa475e7e47b5a1f53c40ae1cf98dbfb8fee0e` |
| `package/source.zip` | `e358aaef40df6e2dc59957a50a9bf4726fcb583f6be56b4b397dc686d9299d2b` |
| `qualification-source/root-host-tests.json` | `fc6a53abc02419d8b29e0ef3581d10e440734b5abc87b5f03374743628a794fc` |
| Original pre-interruption plan | `87d5796d220c7be13c262d9c6498286f4f96ad0871856b2be0c664aa5861b4ea` |
| `recovery-update-plan.json` | `32c9bd70cd4a1ec0115017f3deb361903c52dcc23ed58fa07af29c5d3134fb14` |
| `recovery-current.json` | `ee292c237daac0990bbd6fd1543347a732bf40696b6e3832fdf7b6ccf1fcf7ea` |
| `preparation-recovery.json` | `819fa5d1291d55a4234d0b8d4696b1652de27fb3fe1fb64aef29c4ec609a4736` |
| `prepare.json` | `39b0dacd03efd0bc3e4601d27b441bdf2c05d9c6c8dc6f12ce4eacdf3613228d` |
| `manager-stopped.json` | `4c9fac6d0b04d07e326d0f03a6920f45d520afda5cba5655a08ffc761e23ae54` |
| `apply.json` | `6a4bd36cbccc6b24a664c59968991e5bf4c0cc3b50d0aa5f229aed6218c7089c` |
| `shortcuts.json` | `9629fe935e76325735c3d297176a92249a07c4072f00f8422aea501d5e108445` |
| `activation.json` | `4c989ee5dcbed289d421ad499d68a92d8fce18f0d2f9a998a71303c56caaaa9c` |
| `activation-finalize-correction.json` | `73a1af25654e37f74e2d451c6fca963bf5a23ac339e229323f2a5e6a527b5c03` |
| `launch-receipt.json` | `c966b0b67134aab70a78995bf32dbaf192b29c86edb11f704a9953bb9f26e554` |
| `launch-result.json` | `3b36683cbb3be16338f19f15403796d4f858616ab432e7bf794042df40baddd6` |
| `local-host101-retired.json` | `e4a20d6f9d9d5aef78b7f5b422fe2ebd632f32f2646f582c3bb982676817d8e5` |
| `retirement.json` | `f412796996372b9e7d204b71314174140b7300a5370ecb06121fd954dc45e08b` |
| `post-retirement.json` | `23094a9aff7e70b7347ee7ef0064ff74be5c7598a4cb508435e01184435bc08e` |
| `delivery-index.json` (15 evidence members) | `829370982bd9653b30e14cdecdf7c621a441139851cce82c0b1876c0f214ff83` |

Native source remains `92bd3e90b9d248733915fc5860835fffc5ea4e6e`, version
1.8.65, DLL SHA-256
`8e7d05d024fb988c498059e4e70fbe6e906a81fac4bf4b3ef80caba5e7e57775`.
The approved payload has 23 members. Actual application and activation verify
zero client-inventory changes and no client-file writes.

## Installation and live limits

The original preparation installed the .102 environment but rejected its final
client-lifetime comparison after the visible Umbra client 4092 closed. No prepare,
stop or apply receipt was produced by that attempt, and the .101 active runtime
was not switched. The failed validation evidence remains preserved.

Fresh baseline `ee292c23` observed the same windowless game 3408 and exact .101
manager 1956/parent 5264, with no bound workers. It retained 9,623 rows with no
added/removed paths. The reviewed baseline-only plan revision `32c9bd70` kept the
qualified software and native/client payload unchanged. Recovery reused the
existing .102 environment without reinstalling, validated all 491 module files,
and produced `existing_host_revalidated_not_switched` plus `prepared_not_applied`
receipts. Independent recovery review passed; no client changes or rollback
copies were created by recovery.

Normal stop, application and shortcut verification completed against revised
plan `32c9bd70`. Activation independently verified all 491 installed modules and
9,620 stopped-capture retained records, with zero exclusions. The two typed
activation changes are the manager startup record and dispatch permit. Manager
4652/parent 3980 is healthy with zero bound workers before the next launch.
The existing windowless game 3408 retains creation identity
`134361520773889775` and the exact .65 DLL; no client files were written.

The first activation started the manager successfully, but the private validator
incorrectly required inactive capacity slots that production intentionally hides.
A separately reviewed validation-only finalizer corrected that expectation and
verified the already-running manager. It did not rebuild or restart the runtime
or modify the sealed payload. The correction receipt links the original failed
validation and final activation. Future private updates use the corrected
`activation-recovery/activation_checks.py` template recorded in `PLAN.md`.

The reviewed launcher created game 6832, creation `134362063150691379`, window
394196, with the exact .65 DLL loaded; old game 3408 remains unchanged. The
initial launch capture showed a healthy manager with no bound worker at login
and no active or queued operation. Historical worker 1584 was stopped and unbound;
that capture did not establish .102 worker readiness or in-world buff coverage.

Local retirement verified 491 old module identities and removed the exact .101
`package/installed-wheel` tree and two .101 wheel copies: 1,859 files totaling
35,680,712 bytes. Current .102 software, native B65 and diagnostic evidence remain
preserved. Guest retirement removed the one obsolete .101 host directory: 2,173
files totaling 49,069,543 bytes. Its native-payload removal list is empty; current
.65 native software was not retired. User data and diagnostic evidence remain
preserved, with no rollback copies.

The final postcheck verifies the same manager 4652, new game 6832, preserved game
3408 and exact .65 DLL. Worker 5736 is now attached and healthy, with no active or
queued operation. Character identity is unavailable at login and buffs are paused,
not current in-world coverage. Fresh login/group readiness and a new live command
remain pending; launch and retirement do not establish movement or arrival.
Preservation is evidenced by the stopped-capture/activation receipts; no ancillary
retained-manifest export is claimed.

The preceding .101 command was received and admitted but failed before route
dispatch with native producer-heartbeat expiry (age 1,031 ms, renewal wait 0 ms).
The capture does not identify the exact preceding host call that stalled.
This correction addresses the demonstrated source coupling; a fresh live command
must establish movement/arrival separately. Historical receipt index:
`artifacts/bot-deploy/20261011-host101/listener-ready/come-result-index.json`,
SHA-256 `9f9e45e5bab4b7db2babe9039baa03fc14b5007c25244b6d2a8995fa14f34f9c`.

Delivery documentation is prepared on
`codex/worker-renewal-delivery-20261011` in `bot-runtime`, targeting `main` through
PR [#165](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/165).
Source, qualification, activation, launch and retirement verification are
complete. Fresh live acceptance remains. The deployment policy forbids
retained rollback copies; preserve user data and diagnostic evidence in place.
