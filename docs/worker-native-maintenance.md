# Worker current authority and native maintenance

Host .102 leaves native .65 unchanged. The preceding .101 live `/come` was
received and admitted, then failed before route dispatch with
`native movement renewal failed: NativeActionChannelBusy`, native host lease
expiry, heartbeat age 1,031 ms and renewal wait 0 ms. The request was
`75c7bc14-24e3-444b-82e6-614edaf6bcb8`. Private evidence is
`artifacts/bot-deploy/20261011-host101/listener-ready/come-result-index.json`,
SHA-256 `9f9e45e5bab4b7db2babe9039baa03fc14b5007c25244b6d2a8995fa14f34f9c`.
The native trace confirms ownership expiry, but contains no heartbeat history
or host transaction timing that identifies the exact delay.

The demonstrated source coupling was concrete: active renewal followed locked
historical inbox reconciliation and synchronous status/heartbeat publication.
The operation's parent stop check repeated those reads inside strategy and native
maintenance. A ledger transaction can wait longer than both the native lease and
an existing manager permit. Merely moving renewal to another thread would leave
current authority dependent on that historical scan.

## Current authority

Before any worker-owned native initialization, cold recovery creates or reconciles
one bounded `stop-control.json` per manifest slot. Its strict schema 1 includes
exact node/client identity, an atomic revision token, and a bounded pending set
of typed Stop/Cancel envelopes with a `preparation_pending` flag.

Stop/Cancel submission publishes the durable intent before the atomic envelope
and preparation control. Recovery materializes an interrupted envelope publication
and applies the existing preparation latch. Unreconciled intent blocks same-instance
preparation even after the envelope deadline; finite-operation cancellation still
matches the exact worker identity and original deadline. Resume first recovers
intents, then records the exact superseded stop IDs. A terminal receipt commits
before its exact pending entry is removed. Missing or malformed current authority
does not become an empty inbox. User settings and historical receipts remain in
place; this is current control state, not a rollback copy.

An operation validates its initial authority before native acquisition. Its
independent current-authority observer reads the original atomic manager permit,
the bounded stop set and preparation control through a stable revision bracket,
plus exact retained game/worker stop identity. It does not lock or scan operation
history, reconcile transactions or write status. Group operations also honor the
existing positively observed enable state; ordinary finite operations do not
inherit a historical preparation-disabled state.

The native maintenance thread and strategy stop checks use only the immutable
last-observed permit and first-cause stop latch. Permit expiry is the original
manager deadline, never a new observation TTL. A blocked observer cannot borrow a
newer unseen permit or revive a stopped owner. Explicit Cancel/Stop, group disable,
exact identity loss and native failures retain their existing authority.

## Completion and validation

Observer and maintenance threads belong to one executor lifetime. Existing
`OperationMovement` locking serializes renewal with terminal session disposal;
once closed, no callback can renew that session. Cleanup remains the original
owner's responsibility, including pending native obligations. Failure causes are
not replaced by later cancellation or cleanup messages.

Focused tests cover recovery between intent/envelope/control writes, expired
unreconciled intent, Resume ordering, repeated Cancel while preparation is already
disabled, immutable target/expiry checks, and current reads without history or
ledger locks. Actual movement tests hold the ledger beyond both the native lease
and initial manager permit while newly published and observed permits maintain
the same owner; a separate blocked observer test proves unseen permits cannot
extend authority. Worker-loop tests preserve prestart rejection, explicit stop,
settings disable, game identity, native loss and first-cause cleanup behavior.

Independent source review passed. The focused suite passed 173 tests with the
qualified native movement fixture and no skips. PR #164 is merged after all
15 hosted checks, and the exact composed .102 release passed qualification.
[Delivery evidence](worker-renewal-delivery-20261011.md) records the package;
installation verification and a fresh live command remain pending. Passing these
tests does not establish live arrival or prove which earlier host call caused the
captured producer-heartbeat expiry.
