# Group-command observation and admission

The live .98/.63 receive test identified Pro and `/come` correctly, but the host
refused admission before creating any movement operation. The old error combined
the five-second receive deadline and the 500 ms observer freshness check, so the
record does not establish which elapsed boundary caused that refusal.

Separate passive measurements found native observations at 4-158 ms (including
first open), population reads at 2-5 ms, and worker ledger reads at 3-46 ms. These
samples do not reproduce either expiry and do not justify extending a timeout.
Private evidence remains under `artifacts/bot-deploy/20261010-group63/listener-ready`:
`source-timing.json` and `ledger-timing-index.json`.

The source review found a definite admission race: `pending()` could return a
fresh command, then ledger work could age its observation before `claim()`.
`claim()` marked it taken before testing freshness, permanently consuming the
intent even though no operation had been requested. The correction preserves
that intent on temporary observation expiry and waits for the ordinary observer
to refresh. The original five-second receive deadline still applies. Expired
commands, changed identity, disabled commands, and unavailable group authority
remain refusals. Once admission starts, consumption remains one-shot; ambiguous
submission is never retried. Active operations retain their existing current
permission checks.

Blocking control reconciliation now precedes native observation. The final
native scene must still be bound, nonterminal, current, and in the same epoch.
The observation keeps its original sample timestamp rather than claiming that
previously read member positions became newer at publication. Waiting and
refusal details distinguish observation age from command age.

Regression coverage delays the real worker path between pending and claim,
verifies no initial operation, refreshes evidence, and verifies one submission.
Additional cases cover deadline, group/enable changes, and invalid final scenes.
The combined .99/.64 release also corrects the Track close-function thunk.
Live movement and automatic Track presentation remain pending qualification,
installation, and a new user command; the previous receive must not be replayed.
