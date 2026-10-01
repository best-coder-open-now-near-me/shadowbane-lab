# Native service ownership across delayed updates - October 1, 2026

## Observed failure

The previous host 0.3.61/native 1.8.41 queued Shot to the Leg, then lost the native
movement Grant before ATTACK entered. The original bounded acceptance remains
not passed. Passive schema-3 telemetry retained the exact cause: generation 3 to
4/NONE, reason `stalled`, a 297 ms owning-update interval, key bits zero and
valid foreground/native/scene gates. The user reported no interaction. This
identifies the policy that revoked ownership, not what delayed the client frame.
See the [installed readiness receipt](native-power-readiness-20261001.md).

## Ownership boundary

Installed host 0.3.62/native 1.8.42 distinguishes a delayed client frame from a
lost producer. A service-only native obligation may keep its exact Grant across
a delayed update only with fresh proof of the original pinned native service,
current producer lease, owner thread and native lifetime. The permissive cleanup
admission predicate is not sufficient proof.

Active navigation and unknown owners retain the existing 250 ms discontinuity
policy. A failed stop preserves whether its obligation was service-only before
movement/activity flags were cleared; a stale route cannot acquire that status.
Pending cleanup grants no movement or new native action. Clock regression, lease
loss, scene replacement, focus/UI loss and player takeover remain cancellation
boundaries. Delayed frames integrate zero camera time. Nothing reacquires the
Grant, replays a skill, changes hotkeys or uses system-message text.

## Delivery and remaining work

[PR #58](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/58)
merged at 20:29:16 UTC on October 1, after all 15 hosted checks passed at approved
head `3cc3101`. Main is `8fa16aa4d4d6da2dabf8afe2e26418048ac9fcd0`.
Its included [PR #57](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/57)
receipt was marked merged at 20:29:18 UTC. The qualified .62/.42 runtime is now
installed; package source and later documentation heads remain distinct.

Independent reviews passed. The production input regressions cover ordinary and
delayed updates, physical keyboard and captured world drag, configured remapping,
modifiers, opposing keys, camera-only input and neutral rearming. Native intent
recognition can revoke pending automation without admitting camera or movement
writes or requiring the basis/terrain queries that pending cleanup blocks.

Exact package source is `7f37ff53e181288ce1ae695f2e2699ecf2bb8ff2`, in private
`artifacts/b42/d87717cd`. Later documentation commits do not change that stamp.
The earlier `c85a17d` qualification was stopped after review added mandatory native
owner-service and mouse gates; its partial logs remain, and it was not qualified.

| Qualification | Result |
| --- | --- |
| Complete host suite | 4,397 passed, 788 subtests passed, 37 skipped; Ruff passed |
| Each native profile | 205 passed; all 107 required native gates passed |
| Each profile's real movement/combat IPC | 73 / 86 passed, no skips |
| Power-readiness image probes | 22 cases on each original/prepared image in each profile |
| Package verification | 64 steps and 90 indexed artifacts verified against Git archive, ZIP and wheel |
| Private acceptance/deployment helpers | 90 / 12 offline tests passed; PowerShell/path checks passed |

The three native private-image cases skip in the generic suite and pass through
separate exact-image steps. Both previously deferred renderer transparency
findings remain recorded per profile; they are not combat gate passes.

| Artifact | SHA-256 |
| --- | --- |
| Package | `ee9d05db8475637512499918e10755d294815ff41e3153d27fe2bbb102086e4c` |
| Receipt | `0bc6084f3913c30f39bdb4cb7c21ebc1a9abb5eebac5fc097e5f87877a02a6aa` |
| Full DLL | `4a7fce6cd64cd3619fc937d30eee1291052e5f0f9f8054eee39c43f7b4d40dd2` |
| Host wheel | `d17461b1c232a252e9cba95618263194bdb3875b17b7925606da2e763320ff22` |

## Installed receipt and bounded live acceptance

Installation verified 455 modules, 9,571 preserved files and one DLL inventory
change. Manager PID 8392 was healthy; all five shortcuts and startup preflight
passed. The first preparation validation was read-only and rejected a diagnostic
snapshot whose timestamp strings had been normalized by a PowerShell JSON
roundtrip. No runtime replacement or manager-stop receipt had occurred. Preserving
the fresh raw JSON corrected the snapshot; an independently reviewed resume
verified shared/installed payload hashes and reran validation before replacement.
Retry diagnostics remain retained.

The user-authorized stale PID 9224 (creation FILETIME `134353565789124161`) was
closed and verified before deployment. Launch at 20:34:42.8062291 UTC verified
PID 9380, creation FILETIME `134353604742065321`, HWND `2622084`, and the exact
full DLL hash above. Fresh passive Umbra readiness showed owner NONE and scene 1.
NPC preflight passed with two eligible candidates and health 95%. The later live
run started with full native health/mana/stamina and passed the bounded gate below.
Launch and preflight alone are not combat acceptance.

The inspected obsolete .61 host contained 2,100 files / 47,672,015 bytes. Removing
it and two exact obsolete .41 payload binaries reclaimed 50,365,297 bytes; four
old host/share staging binaries accounted for another 5,386,564 bytes. Settings,
jobs, saves and diagnostic evidence were preserved, with no rollback copies.
The local export under `artifacts/bot-deploy/20261001-b42/receipts` verified twelve
compact receipts and seven installed-file hashes.

The preserved private run `npc-recovery-readiness-171aeadcf4c44bd19a38876e94c87ef4`
passed independent trace and receipt review. Compact evidence hashes:

- Acceptance: `79925ad941600917483bd489536ee65283efc7fb8d85d2cc0d4dbc90c8311cb1`.
- Events: `cc16dd30cbb251d15dde2182c139fd022665f787867edf96036e8987c83f991e`.

| Trace gate | Observed proof |
| --- | --- |
| First encounter | SELF_POWER request 1 and ATTACK requests 2/3 queued in engagement 1; request 3 was a bounded same-target renewal. |
| Death and cleanup | Step 65 observed the original NPC key/token at native health zero; step 74 confirmed cleanup with STOP request 4 / NATIVE_STOPPED. |
| Recovery | Step 75 was strictly later production SEEKING; the next encounter used a distinct key, token, address and engagement. |
| Optional opener fallback | Second SELF_POWER request 5 returned POWER_REUSE_BLOCKED, NEVER_ENTERED, BOUND, cleanup-only flags; step 77 recorded power_reuse skip and queued ATTACK request 6 under that same binding. |
| Terminal cleanup | Intentional harness stop after the second queued attack; step 79 confirmed STOP request 7 / NATIVE_STOPPED, mode 1 and no AF8. |

Both encounters retained the same exact producer/Grant (generation 3, scene 1).
Final combat owner was released and manual-list membership was zero; no error,
observation failure, boundary rejection or watchdog occurred. Loop timestamps are
observation timings, not measured action latency. The original evidence remains
unchanged. Its inherited conservative `pve_recovery_claimed=false` metadata is
separate from `production_recovery_observed=true` and the independently verified
trace ordering. This is no claim of second-NPC death, server kill credit, skill
consumption or snare application.

Active next item is [automatic buff qualification](buff-preparation-20261001.md).
That work continues on `codex/native-buff-preparation-20261001` through draft PR #59,
now based on main; no buff action or module is claimed. Both merged runtime and
receipt branches were retired locally and remotely after verifying their tips in
`origin/main`; the clean runtime worktree is detached at `8fa16aa` for reuse.
Automatic retaliation remains disabled.
