# Automatic buff live acceptance — October 2

Installed host **0.3.66** / native **1.8.46** use qualified source
`9e1a77ae9e763a65bfc7f39587c30b3f46c39c4b`. PR #62 integrated the runtime;
PR #63 integrated the installation record after all 15 hosted checks passed,
as merge `6373cfd6aff4bb6fd39c57e3c654297f435f21f4`.
The [deployment policy](deployment-policy.md) remains mandatory.

## Buff application observed; encounter acceptance incomplete

Run `actor-full-encounter-7662b3d54ca94dc6a70e11eff14e5613` used fresh Umbra /
Wonderbane identity and the installed qualified DLL. Native USE_ITEM at 562 ms
reported CLIENT_OUTBOUND_QUEUED and local SETTLED for potion object `[5843772,30]`.
Later complete native effect publications established all nine configured potion
descriptors. By event 276 at 26,344 ms, all five requested groups were PRESENT:
concoction, Precision, Beorc Rune, Transform through Rat Shape, and Defensive
Stance. This proves observed coverage in this run, not expiry/refresh or overlap.

The first NPC context, targeting key `[23887,37]`, token
`643533448740a933caa621c2`, returned DEFERRED / CLOSED / NEVER_BOUND. The correlated
STOP_CONTEXT confirmed NEVER_BOUND. After buffing, production attempted a fresh
context for that same key, token, address and parent. The private acceptance
helper rejected the new context ID as a second NPC before sending it. No ATTACK
or Shot to the Leg was submitted; recorded target health remained 800. There is
no NPC death or server kill-credit proof from this run.

Final STOP_OWNER request 82 returned CLOSED / LOCAL_RELEASED with no combat target.
This is local release, not a NATIVE_STOPPED combat claim. A subsequent passive
read reported owner NONE, no pending cleanup and fresh native readiness.
The original run remains **not passed**. Its private evidence is preserved at
`artifacts/bot-deploy/20261002-b46/live-evidence`.

An earlier attempt, `actor-full-encounter-34002a5076704e73b94b53b6309377e6`,
refused admission before opening an owner or submitting an action. Its combined
initiation/action-target error did not retain the rejected observation, so the
failed predicate is unknown. Four subsequent passive samples showed initiation
state 5, empty protocol IDs and no native action target before the retry.

## Passing bounded encounter

Run `actor-full-encounter-rebind-7a57fd7769404f688fa5fe682a370233` passed with the
same installed runtime. The private successor retained one immutable NPC and
permitted a new provisional context only after correlated NEVER_BOUND closure,
without child action history. Independent review and 116 offline tests passed.
Both original failed runs remain unchanged.

The passing run submitted Shot to the Leg and two positively queued ATTACK
requests against the same NPC. Native death was observed at event 126. Correlated
STOP_CONTEXT request 39 confirmed NATIVE_STOPPED while the parent remained BOUND.
Preparation continued under that parent, all five coverage groups were observed,
and STOP_OWNER request 116 confirmed LOCAL_RELEASED. No target-list entry,
watchdog, unexpected interruption or recorded error remained. Subsequent passive
readiness was fresh, owner NONE and no cleanup pending. This is native-object
death and cleanup proof, not server kill credit or queued-skill consumption.

Beorc was initially missing and was reapplied. Rat was missing and reuse-blocked;
Skree was eligible and later supplied Transform coverage. Its first submission
was definitely never entered because a native target was occupied; a fresh
eligible request subsequently queued and settled. Potion, Precision and Defensive
coverage were already present and remained so; none was resubmitted in this run.
This proves missing-buff recovery and alternate choice, not the cause of buff
loss or a complete repeated expiry/cooldown cycle. Potion quantity remained 3.

Umbra / Wonderbane's reviewed buff configuration is saved and read back at
revision 2. Basic policy and Shot to the Leg opener `563795161` are preserved.
The saved intent enables missing-buff maintenance on subsequent PvE runs; saving
settings did not start an unbounded bot. The compact local settings receipt is
`artifacts/bot-deploy/20261002-b46/saved-buff-settings.json`.

## Remaining work

1. Investigate action-specific potion overlap. The item request settled locally,
   but native state 6 and protocol 429021400 kept admission INITIATION_PENDING;
   Precision was not submitted until 12,141 ms. No fixed host delay was identified.
2. Verify sustained refresh and alternate-transform cooldown behavior across
   complete expiry/reuse cycles.

Automatic retaliation remains disabled. This record contains reviewed findings;
raw captures and client binaries remain private.
