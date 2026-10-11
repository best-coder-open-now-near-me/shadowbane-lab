# Group command authority delivery - October 11, 2026

## Source and qualification

Host .101 separates fresh group-command admission from ongoing operation
ownership. Reviewed source `358234222d51477520e47743497a042fd41b1c91` is
[PR #162](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/162),
merged into `main` as `1a9807c902a0eccc31ad46d032ef7ca3c047b173` after all
15 hosted checks passed at the reviewed source head. Release composition
`4d365500168dd7ad6e819c242598e4d3eec5b9d9` retains installed graphics and the
unchanged native .65 source `92bd3e90b9d248733915fc5860835fffc5ea4e6e`.
This is a host-only update; no DLL, client executable or resource replacement
is included.

The exact composed host suite passed 6,277 tests with 44 optional skips, with a
clean source checkout before and after. All 16 package stages passed and 491
installed modules match the source/wheel closure. Full and diagnostics-only IPC
profiles each passed 76 movement, 86 combat and 245 actor cases. Six installed
desktop cases and one real worker handshake passed; none of these IPC/startup
cases were skipped. Existing non-gating graphics transparency findings remain
unchanged; this host update does not resolve them.

Private qualification evidence is under
`artifacts/bot-deploy/20261011-host101/`:

| Artifact | SHA-256 |
| --- | --- |
| `package/host-qualification.json` | `a8dca07f569c1eaf81fd500391ff23a2b96059467dee0485f698db11c0e0068a` |
| Host .101 wheel | `86977270287c9348e9f835112d40235a4b840b153c0fd2001d08e720eb515994` |
| Exact source archive | `b87f737a8e577fb0ff6bec381535f9c05e71c5c05b3d0e89f5a560e371f868ec` |
| Unchanged native .65 DLL | `8e7d05d024fb988c498059e4e70fbe6e906a81fac4bf4b3ef80caba5e7e57775` |

## Behavior and evidence limits

Fresh current-member and destination authorization remains at claim, with fresh
group authorization again before queued execution. An admitted one-time command
then retains its existing worker/game/scene/native ownership rather than leasing
permission from passive observer freshness or the whole-roster digest. Explicit
Pause, disable, Cancel/Stop and newer-command preemption remain effective, as do
player-attack exact-target protections. Consumed-command acknowledgement keeps
active/completed commands from later being reported as expired before admission;
durable observer writes cannot hold the worker's setting-read lock.

The installed .100/.65 Treehugger `/come` was received and admitted but failed
before routing with `group command permission changed; native_movement_owner_revoked`.
Sampled group identity stayed stable. The exact failing host predicate at that
supervision tick was not captured, and the evidence does not establish that the
host check caused native revocation. The demonstrated defect is that unchanged
observation age 500 ms permits execution but 501 ms fails the old ongoing check.
See [the source and live evidence](group-travel-continuity.md#admission-authority-correction---october-11).

## Verified installation and next acceptance

Normal host preparation, stop, apply, shortcut update and activation completed
against plan `6abf9c33b7aa3206ac3729a58fe9d7abbebe7a35fb398ef4f202eed31d796333`.
Apply retained 9,614 records and wrote no client files. Activation verified 491
installed modules, the same 9,614 retained records, zero exclusions and ten typed
startup/worker-record changes. Preservation is reported from these validated
phase receipts; no additional retained-manifest export is claimed.

The new manager is PID 1956 (creation `134361723393950442`), parent 5264
(creation `134361723392414345`), with worker 1584 bound to the same game 4092
(creation `134361669173785291`, window `66496`). The second game lifetime 3408
(creation `134361520773889775`, window zero) was also retained. Both still use
the unchanged native .65 DLL. Activation reports a healthy manager with one
bound worker; no game restart, client-resource replacement or rollback copy
was required.

| Installation receipt | SHA-256 |
| --- | --- |
| `prepare.json` | `ac318fe60be20c787f3bfd67ef3749f58094b87768e86409ac8eee38afeaebb5` |
| `apply.json` | `32a7e50a19411fe2b116072497cf8a55294cd215da85bf8f21692c23ece16116` |
| `shortcuts.json` | `376d6a9c9b461bcdf8830133aa2bf28285503642d60fc92ee00b182d6a209faf` |
| `activation.json` | `0d999f9185cadb94f471fd16e3c137d2189885ca45e2442690204ae5dc6e4ab3` |

The fresh .101 Treehugger `/come` was admitted but failed before route submission.
Its native action renewal found a heartbeat 1,031 ms old with zero milliseconds
spent waiting inside that renewal call. The native owner changed from automation
to none after 1,625 ms, on a 125 ms client sample interval. Travel recorded one
step, zero dispatched actions and no arrival. No retry or buffered replay was
issued. Upkeep was idle in the post-terminal capture.

Private correlated evidence is `listener-ready/come-result-index.json`, SHA-256
`9f9e45e5bab4b7db2babe9039baa03fc14b5007c25244b6d2a8995fa14f34f9c`.
The exact blocking host call was not timed. Source review separately established
that active renewal still performs repeated historical operation reconciliation
and inbox scans under a shared five-second lock, despite the one-second native
producer lease. The next source work separates bounded active authority from
history/control I/O; merely widening a timeout is not the planned correction.
Fresh live arrival acceptance remains pending.

The obsolete .100 host was retired after verified activation: one directory,
2,173 files / 49,065,694 bytes. Both game lifetimes, manager 1956, worker 1584 and
native .65 remained unchanged. No native package or payload was removed. The
postcheck found upkeep current and maintaining again without another Resume;
the earlier idle capture was transient. The failed travel remains failed.
Retirement receipt `retirement.json` is
`bd760727e0c8bfb1f86f676da39e02e26e5f3ab3e0e8437b654c63cc724d50c4`;
`post-retirement.json` is
`9c55df434473af3bf6cd437d8e002553b19de3baddd1a099092436038df3e487`.

Delivery documentation is on `codex/group-authority-delivery-20261011` in
`bot-runtime`, based on reviewed source and targeting `main`; PR #162 is merged.
