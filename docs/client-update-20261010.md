# Official client 1.3.38.17 alignment - October 10

The official patch supersedes the unactivated host .92 plan below. Current
source is reviewed PR #148 at `dde99e07534fb129f697bede403672e9cfdec08e`.
Host 0.3.93/native 1.8.60 release composition
`5a46687dce579417f8b8bd086c4c6929a68c513a` is pushed on
`codex/wonderbane-client17-release-20261010` and independently qualified.
Installation is pending; no live .17 acceptance is claimed.

## Exact client and static review

| Image | SHA-256 |
| --- | --- |
| Official 1.3.38.17 | `051c55ebd0f25ff5fe9bd27b25efbe3cde0190d1dbf1c2a33eb9604996c69698` |
| Prepared 1.3.38.17 | `baa6c84e5f28aab01d516f12257354b42375d11e8e8e98930cfcf754aeec24e9` |
| Official patch manifest | `084919129715e16d941c33a2ec7600416fc95f13e2c0ac06441d5959568eb17a` |

The executable remains 21,143,613 bytes. Comparison against .16 found 379
changed bytes in seven ranges, including code changes. At exact qualified .92 source
composition `97c4899b23273e83a596784136b621c17650cee9`, all 16 applicable
production profiles / 51 anchors and 149 literal hashed native spans are
unchanged. Track and group-chat callers, constructors and vtable boundaries
match. Control-flow review found no current hook conflict; it does not establish
unchanged gameplay or server behavior. Independent reconstruction confirms
exactly seven bootstrap writes, with no overlap with the official changes.

New guards admit only the exact reviewed pair. Strict action/session readers
continue to require the prepared image; original and unknown images remain
rejected at those boundaries. Character replacement revocation and unknown-affix
preservation remain enforced. No native offsets or signature spans are relaxed.

Private audit evidence is under `artifacts/client-update-20261010`:

- Binary audit manifest: `75ab2b56faf1f8975ea3460c709314e82600ed8a5e0384b941dd0231c3c50ac5`.
- Binary audit summary: `ad1ff43fa12bf6f7ef6f9fa7a9b864b591100efe48aa76602e9d730c99d9bdbb`.
- Full official/vendor asset inventory: `3f8a67b4b03c5a43b3dcd18250070de68872c3e96f518ba3fd234a50ebaf9572`.

The manifest has 211 entries and exactly five official changes: `sb.exe`,
`Config/Config.wpak`, `Config/ItemENGLISH.txt`, `cache/CObjects.cache`, and
`TreasureTables/ModTables.wpak`. Runtime-written DoubleFusion files and user data
are preserved. The full deployment baseline corrects the earlier coarse census:
no games or workers are running, but the .91 manager is healthy and idle with
no bindings. The normal reviewed manager-stop path applies. The official download
is patched; the vendor runtime still has prepared .16,
native .59 and selected host .91. Inactive .92 preparation is not activation.

## Qualified combined package

All 6,093 host tests passed (41 optional skips). Both native profiles passed
required tests and exact-image probes: full 259 / diagnostics-only 255 native
cases, plus each profile's 76 movement, 86 combat and 237 actor IPC cases. Three
private-image CTests per profile are skipped in the generic run and independently
executed with actual images later in the package. All four group-chat probes
passed their 16 constructor/queue cases. The existing deferred transparency
findings remain diagnostic-only; no required gate failed.

Independent review verified all 140 artifacts and 112 stages, 486 installed
modules, six desktop cases and one real worker handshake. Composition review
confirmed retained graphics and named-camp source plus the source launcher fix.

| Evidence | SHA-256 |
| --- | --- |
| Independent qualification | `b45f0199cbff9bfe48c4fbf3df2fdcc7e1e3b6821ca7a485c952c0b5843c83f4` |
| Builder receipt | `e8e03b6a3ca71e3901562faa752b90e283a3857a9e32a900cbe215d0ef1a3e0b` |
| Package archive | `43490990b2490391b86d5f16ebb9f289ba38b048fd7018bc1d57a7b3588bdb33` |
| Native .60 DLL | `c0a3f2028ecf410b7d959ce9dcf7ad58c5937f04a9c4b5d9a08b25eaca257c12` |
| Host .93 wheel | `7f2fa74210ca2730a9f18780e9272aea76f61db9158b6ba8313733cbd16d5afc` |
| Fresh deployment baseline | `d7d06238c9d62b30aab6bced4302ff99533f5183a1e2b3d4588fa1316426bf26` |

The baseline inventories 9,540 retained records and 486 installed modules.
Inactive .92 remains prepared, with no apply or activation. Installation helpers
passed independent review; their final plan must bind the qualified package.
Private package evidence: `artifacts/b60/ab4666ed`; review/baseline evidence:
`artifacts/client-update-20261010/{qualification,deployment}`.

## Current delivery todo

- Complete: exact image/asset census and independent static compatibility review.
- Complete: reviewed source and full .93/.60 package qualification, retaining
  installed graphics and merged named-camp behavior.
- Active: replace the five changed official assets and native extension, activate
  the qualified host, verify data preservation and launch the test client.
- Pending: after user login, one normal named-camp acceptance run with buffs.

Do not replay the historical .92 host-only plan. Apply the
[no-retained-rollback policy](deployment-policy.md).

---

# Native named-camp host .92 - October 10

## Source and qualification

Native named camps replace the implicit 120-unit NPC admission circle. The
nearest eligible loaded NPC establishes one placed native zone identity;
subsequent same-camp targets and respawns use that identity. An admitted exact
NPC can be pulled across zone boundaries without losing ownership. Missing zone
evidence grants no new target, and an empty camp does not cause roaming. Explicit
manual-radius runs remain supported. Listed-player bounds remain a separate
unchanged policy. See [the operating contract](pve-automation.md#named-camps-and-approach).

Merged source:

- PR #144, head `30d64c478cf5b42e785ea793a44172acb1260a83`, merge `752cae35c1ff9392c794edd1d0d50aff4afb486b`: exact-target cooldown lifetimes.
- PR #145, head `5ef487034cd88550a6995158d67f6da89ae48a85`, merge `8fb26a81046ffd8a4435602ab5641c6c0aa99b14`: native reader, controller and production defaults.
- PR #146, head `5aff646da730e353870bced34bb786bc3f8aab25`, merge `244d3723892dbff3368cac7b93e598e47f0f4ce1`: source listener's explicit-only radius override.

All final-head hosted checks and independent reviews passed. The launcher
follow-up is not used by the installed manager and does not change its package.

Release composition `97c4899b23273e83a596784136b621c17650cee9` combines the named
camp source with installed `faf9d023abc055d1c27a1efa9c69d0af62f1da1f`. Native .59
source/assets equal `3459d173835657d33ca4b07a92342a26bf73bca2`; DLL SHA-256 remains
`0bf82326b29c9a6d593214f8a5e12d0d6950a47e4eb30480ac991ba510dcca89`.

The exact clean composed host suite passed 6,049 tests with 41 optional skips.
Both native profiles passed 76 movement, 86 combat and 235 actor IPC cases.
Six installed desktop cases and one real worker handshake passed. All 16 package
stages succeeded. Independent review verified 1,514 archived source files,
486 source/wheel/installed modules and 140 native artifacts.

Private evidence is under `artifacts/bot-deploy/20261010-host92`:

| Evidence | SHA-256 |
| --- | --- |
| Host attestation | `6104f612a8c0217507db0dd36b6212a605b1590748cbdd2e8d62571073b42b8c` |
| Qualified package receipt | `55e6d39ef8c4c40058cb8446edddd2cdf44e03e9ca0da1929d58d986602d9d27` |
| Host wheel | `78cf79aa40576a6bc61a3834ed42b9b234b1c41c0821c6207c6897f7e1c4eb24` |
| Source archive | `48f5de172da48e1dcb02bae0c8444020be8b39d5ebc764744334ce25d5d5b7c6` |
| Reviewed update plan | `29fdeb740a92df75a8884b5a2f83e9dfcc6908f8943caa58666447cba64d10ea` |
| Preparation receipt | `ba0ca3c892547709b354b1650041e0927cba6795beaffeb72de6752cd2d8997c` |
| Interrupted-state evidence index | `a770fad7bac7430eea2095c7f18d638e802a62bffb526a6e069a0fdafd5eb8c5` |

## Actual installation state

Preparation completed, but activation did not. Normal Pause succeeded; the stop
phase then rejected native publication that did not meet the existing freshness
and quiescence check. It did not terminate the manager or apply the update.
Later inspection found the same game and healthy old worker, paused dispatch,
no active/queued operation, native owner NONE and no pending cleanup bits, but a
stale native publication and unavailable character binding. This is not evidence
of a combat action still running or of a client crash.

Host .91 remains selected. Prepared .92 has not been activated. No apply,
shortcut change, native replacement or retained rollback copy occurred.
The baseline captured before the long interruption must be refreshed before
continuing. The user has been asked to bring Umbra into the world and confirm
readiness. No automatic Resume was issued against an unavailable character.

Next: verify current character/publication, refresh baseline and review the
resulting exact update plan, finish host-only installation, verify preserved
settings/history and ordinary upkeep, then perform one bounded normal camp run.
The prepared acceptance helper must be bound to actual activation receipts first.
No live named-camp combat acceptance or movement completion is claimed yet.
Follow [the no-retained-rollback deployment policy](deployment-policy.md).
