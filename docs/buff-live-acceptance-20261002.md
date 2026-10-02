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

## Remaining work

1. Qualify the private helper's same-NPC context retry only after exact prior
   NEVER_BOUND closure, preserving parent, request, target and action bounds.
2. Complete bounded NPC acceptance and save/read back the user's buff settings.
3. Investigate action-specific potion overlap. The item request settled locally,
   but native state 6 and protocol 429021400 kept admission INITIATION_PENDING;
   Precision was not submitted until 12,141 ms. No fixed host delay was identified.
4. Verify refresh after expiry and alternate-transform cooldown behavior.

Automatic retaliation remains disabled. This record contains reviewed findings;
raw captures and client binaries remain private.
