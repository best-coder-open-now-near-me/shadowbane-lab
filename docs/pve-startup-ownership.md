# PvE startup ownership

The manager reserves a finite operation before starting its PvE setup. It acquires
native movement authority only after character-bound readers, terrain navigation,
trace journal and observation setup finish, and after the exact character and
client window are revalidated. The direct CLI already acquired at that boundary;
the manager now supplies its acquisition callback there as well.

This addresses the October 10 run that failed before its first world observation:
its trace selected no camp, target or movement proposal. Native boundary evidence
recorded automation acquisition followed 2,829 ms later by a generation change
with the `stalled` reason. That evidence does not identify every possible cause of
an expired producer lease. The source defect is that the manager exposed its lease
to slow startup work before the runner could begin.

The reserved operation remains visible to cancellation and maintenance throughout
setup. It prevents another finite operation from taking its place. Before native
acquisition, maintenance has no grant to renew. Cancellation or failed setup closes
the unused session without issuing a native stop. Once acquisition is attempted,
the original request, correlated refusal and ambiguous-outcome cleanup rules remain
unchanged. The manager retains native acquisition exceptions instead of reducing
them to an ordinary CLI error code.

Lease durations, native admission, exact process/window safety, and terminal
cleanup requirements are unchanged. This is a host-only correction (.94); native
.60 is unchanged. It does not clear a previous unconfirmed cleanup or claim that
the failed live operation was resumed.

Regression coverage exercises the actual manager-to-CLI setup boundary, exact
identity changes during setup, cancellation before acquisition, duplicate operation
reservation, maintenance before and after acquisition, and immutable acquisition
failure evidence. The existing real native movement fixture also covers grant
acquisition, renewal and exact terminal stop.

Source is developed on `codex/pve-startup-ownership-20261010`; integration targets
`main`. Runtime qualification and live acceptance remain separate from source
validation, and the release composition must retain the installed graphics work.
