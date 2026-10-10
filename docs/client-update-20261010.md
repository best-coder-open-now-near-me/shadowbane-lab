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
