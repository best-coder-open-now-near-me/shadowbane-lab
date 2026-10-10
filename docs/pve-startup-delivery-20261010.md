# PvE startup ownership repair — October 10

## Observed failure and repair

After the user explicitly resumed the NPC test, the installed .93/.60 runtime
started operation `operation-ad9e1092e773496fbfedf8c20d58b128` on Umbra in
Wonderbane. The census found six eligible Connauch Henge NPCs with placed zone key
`[578,79]`, 142.6–175.2 units away. These were observations, not a new range gate.

The operation stopped before its first encounter-loop observation: the sole trace step had
no camp, target or action proposal and zero confirmed deaths. Native ownership
retired as stalled 2,829 ms after acquisition, with a 110 ms update interval and
no recorded manual/focus/UI/scene revocation. The exact original producer lease
failure cannot be reconstructed from the later empty producer header. This is
not a combat or named-camp admission result.

The manager acquired control before reader and terrain setup. Host .94 now
reserves the operation during setup and acquires only after exact client
revalidation at the existing direct-CLI boundary. Cancellation and setup failure
before acquisition require no native stop. Native refusal and ambiguous receipt
handling remain unchanged; no timeout or native admission was relaxed.

Failure evidence is private at
`artifacts/client-update-20261010/deployment/camp-run/failure-evidence.json`,
SHA-256 `020cd35de53a246429e0810bbaa64d0ce683470ac1c73bfcaf2c491762dd0691`.
The later owner-NONE and drained queues did not fabricate a successful cleanup
receipt. Automatic buffs remained held pending the qualified repair.

## Qualified source and package

Source PR #150 has reviewed head `abef6241d4f81904aa736ae3f72eed470345e02e`.
Its merge of current main adds only the prior delivery documentation; runtime,
test and build inputs remain identical to reviewed `d650b226`.
Release `c27a7da62b8103900022f6f2c9edd5f79448cec0` is published on
`codex/pve-startup-release-20261010`, retaining installed graphics and exact native
.60/assets from `5a46687dce579417f8b8bd086c4c6929a68c513a`.
Main remains the shared development destination; the composed release is not a
new shared base.

Independent source and package reviews passed. The exact clean release passed
6,099 host tests with 42 optional skips; both native profiles passed 76 movement,
86 combat and 237 actor communication tests without skips. Six installed desktop
cases and one real worker handshake passed. All 16 package stages passed, and all
486 source/wheel/installed modules matched. The initial full-suite failure was
seven stale test fixtures; their corrected acquisition setup retains the original
cancellation and cleanup assertions. Its diagnostic evidence remains under
`artifacts/bot-deploy/20261010-host94/attempt-0980b197`.

| Evidence | SHA-256 |
| --- | --- |
| Exact full-host attestation | `a6dd24a2d0329d34d705957b2140a7eac8d7c80eb225bf1880d060d63322dc70` |
| Qualified package receipt | `f444e2ab06e688b3f7964db545185fe70f6087ef467e59fe871a6b913ecb6470` |
| Host .94 wheel | `d38370f0cf61318b623e56bdec1d50d8a3e95c9f71fcc391ce6b78adc4540c92` |
| Exact source archive | `feb312489316b10415feba912e4de613fe8124e8a20701d19856e26501bf375c` |
| Unchanged native .60 DLL | `c0a3f2028ecf410b7d959ce9dcf7ad58c5937f04a9c4b5d9a08b25eaca257c12` |

## Delivery status

Qualification is complete. PR #150 merged as
`c9a3dfc6d95c1bfd89c954c8e6f0d8d3b13a0849` after all 15 final-head hosted
checks passed. Host-only apply, shortcuts and activation are independently verified.
The same game process, lifetime, window and .60 DLL remain in place. Apply made
zero client-file writes or inventory changes. Activation verified 486 modules,
9,548 stopped-baseline retained records, zero exclusions and ten typed generated
changes. The separate retained-manifest export was blocked by automatic approval
review; receipt-level preservation is verified, but independent row-by-row
reconciliation of the earlier 9,550-row running baseline is not claimed.

The normal named-camp retry passed; obsolete .93 software retirement remains pending.
No retained rollback artifacts are allowed under the
[deployment policy](deployment-policy.md).


| Deployment phase | SHA-256 |
| --- | --- |
| Reviewed update plan | `a5debbc42550cb405aadd4d5e4e64c8c2b882f9b3d7f1651d538dae7416d676d` |
| Prepared host | `e152ab4e041fa178c719167174f485fdd8a58755c7a91e30f712612d4b66756e` |
| Exact manager/worker stop | `2757dd8df37d34e02a26aeac84b4916df2c227650e212af8aef9b4bedc638fbc` |
| Apply | `f1fdb20ffd78bebae08bb6afdbc391a6376543511917926d52c255b2f4bd14b1` |
| Shortcuts | `2e0b0b5ce58ee3ac517cfc61a0e029b45e18f4bbece798eb49499fce613d9b1a` |
| Activation | `87721d80b5bcb925357aa52457ba19744be326bb16ea94c65d08542c67ad84af` |

## Normal named-camp acceptance

The user-authorized one-minute production run completed on the same Umbra client,
with worker 6424 and operation `operation-41421b5ce2cf4f7ab201773a33aba22c`.
A fresh census contained six eligible NPCs, all in Connauch Henge at placed native
zone key `[578,79]`, all beyond 120 units. Named-camp admission selected three
exact NPC lifetimes. Their native health reached zero at 5.984, 26.594 and 47.750
seconds; corresponding cleanup was confirmed at 7.250, 27.859 and 48.922 seconds.
This proves three NPC deaths, not exclusive kill credit.

The complete 82-step journal reports success and requested cancellation. The
supported cancel succeeded, active operation became null and the queue was empty.
Resume was issued only after correlated native cleanup was verified. Approach
records show 20 yielding and 13 idle observations, with no error; ranged combat
progressed without route driving, so movement completion is not claimed.
A subsequent passive status sample confirmed all five buff groups present,
current and maintaining, with no pending application, no admission blocks,
a healthy worker and no active or queued combat. The immediate post-Resume
snapshot preceded the next heartbeat and was not used for this coverage claim.

Independent review verified the raw journal at
`E:/virtual-machines/shadowbane-testing/diagnostics/pve-chat-20261010-151052-1791659452539959800.json`,
SHA-256 `b2d6738c747a7b0194e4b129ccabe7b7f9652fe5556ece07ca45fe1cca98efa9`.
Cleanup, cancellation, status and Resume receipts are private under
`E:/virtual-machines/shadowbane-testing/diagnostics/host-update-20261010-0.3.94/camp-run/run-89bc9dbdaf154a0e9143ac7690c173eb`.
