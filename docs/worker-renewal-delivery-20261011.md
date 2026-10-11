# Worker renewal delivery - October 11, 2026

Host 0.3.102 is merged and its exact release is qualified. Preparation recovery
is verified; active installation is still pending. Native 1.8.65 and client
resources remain unchanged by this host-only package; fresh live `/come` arrival
acceptance is still pending.

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

Native source remains `92bd3e90b9d248733915fc5860835fffc5ea4e6e`, version
1.8.65, DLL SHA-256
`8e7d05d024fb988c498059e4e70fbe6e906a81fac4bf4b3ef80caba5e7e57775`.
The approved payload has 23 members and specifies zero client-inventory changes;
that plan is not proof that application or activation has completed.

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

Normal stop is underway. No .102 activation, post-switch process identity,
retained-record total at application, obsolete-host retirement or live movement
success is claimed yet. Final application/activation receipts will be appended
before reporting the runtime installed.

The preceding .101 command was received and admitted but failed before route
dispatch with native producer-heartbeat expiry (age 1,031 ms, renewal wait 0 ms).
The capture does not identify the exact preceding host call that stalled.
This correction addresses the demonstrated source coupling; a fresh live command
must establish movement/arrival separately. Historical receipt index:
`artifacts/bot-deploy/20261011-host101/listener-ready/come-result-index.json`,
SHA-256 `9f9e45e5bab4b7db2babe9039baa03fc14b5007c25244b6d2a8995fa14f34f9c`.

Delivery documentation is prepared on
`codex/worker-renewal-delivery-20261011` in `bot-runtime`, targeting `main`.
Source, qualification and preparation recovery are complete; active installation
verification and fresh live acceptance remain. The deployment policy forbids
retained rollback copies; preserve user data and diagnostic evidence in place.
