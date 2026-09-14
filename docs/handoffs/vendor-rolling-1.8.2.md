# Vendor queue-fill candidate 1.8.2

Exact package source: `8aad37fcf691e05ae49960f939cab8ceba43a299`, branch
`codex/vendor-rolling`. Product 1.8.2, wheel 0.3.2. Integration destination:
`codex/native-lifecycle-hardening`, then reviewed `main`. Neither merge occurred.
The normal project checkout remains clean on main at `047147d`.

## Behavior and remaining qualification

Typed native inspect/Create/Keep commands run on the existing native owner
thread, with process/scene, window, menu, vendor and request checks. The durable
host batch fills current free slots one request at a time. Rank growth extends
the recorded capacity and plan, including growth while a request is pending.
It stops once the queue is full; it does not refill completed slots indefinitely.
The latest live read found Malik (2517204) with three empty production slots,
after the owner ranked up the vendors. Random recipe selection was not open.
The schema bounds observations at 16 slots; greater capacity is rejected,
never truncated or treated as a full queue.

A successful native call is a local submission. A correlated, unambiguous queue
addition is required before the next Create. Lost receipts, ambiguous additions,
logout, shrinking capacity, unrelated item changes and disk failures stop new
submissions. Existing journals are never replayed. The process-local native ledger
retains up to 4096 mutation requests and then refuses further mutations.

No automatic game command has yet been issued. The native invocation is pending
live qualification in this exact package. Manual Create, Keep and inventory
reconciliation have already been observed. Automatic completed-item handling and
Junk are unfinished. The affix rule remains exclude confirmed Tier 1/2 and keep
unknowns; unknown on either side overrides a known low tier. The tier reference
has no Tier 1 rows and native token-to-name mappings remain limited. Never claim
complete low-tier recognition or enable disposal from guessed names.

## Exact package and validation

Private package root: `E:/Projects/shadowbane/artifacts/vendor-packages/8282d303`.
Receipt: `diagnostic-manifest.json`; archive: `navigation-inspector-diagnostic.zip`.
All 60 recorded file hashes/sizes and ZIP CRC verified.

| Artifact | SHA-256 |
| --- | --- |
| ZIP | c9b8f7e0f34bab449ec1a00c2d9f7a324219cbe6965c4d92cc55aa4b7ca9662e |
| Full DLL | 36af3f936bbcfd2a919fd4fa06697c52ef40dad4677dc13b7f0bbcf74a05e39f |
| Diagnostics DLL | 6a49bd06c8aa0f34fcbd56c4945b500db5c88e3734fd1d0b36c8f37c254d2b8b |
| Wheel | f62ecfc6fe5a523850650087a2b782aa9669e9de2cf62ee3923421a8ec73b2be |
| Bootstrap manifest | c81b508090fbb3bac1b6fe0b54a883f5501c6d10927d5336391b3e20b463f9ed |

Exact builder: 2104 Python tests passed, 12 skipped; whole-tree Ruff passed.
Both Win32 profiles built, each with 142 native required passes and three
no-argument binding skips covered separately by explicit selected-cue, sky and
original/prepared movement image checks. Each profile also passed 63 IPC tests.
The vendor controller, native reader and channel tests are mandatory package
gates. Installed-wheel entry points, panels, readers and vendor contract passed
outside the checkout. C++/Python vendor wire compatibility and repeated capacity
growth during/between requests are covered by the Python suite.

The two previously recorded ideal-transparency diagnostics still fail in both
profiles. Findings remain in the diagnostic receipt; this is not full graphics
acceptance. No such failure is waived from the required vendor/runtime gates.

All seven CI jobs passed for this exact source:
https://github.com/best-coder-open-now-near-me/shadowbane-lab/actions/runs/34840890085

Earlier package root `a8484967` stopped at a missing Python `build` dependency.
It is retained as failed evidence, not an installation candidate. The documented
build dependencies were installed locally; the complete builder reran into the
new root above. Native build scratch remains under the vendor worktree's ignored
`artifacts/vendor-native-build`; private VM inputs remain outside Git.

## Test VM preparation

New separate destination: `S:/ShadowbaneLab-Guided/vendor-1.8.2-8aad37f`.
Inputs: `E:/virtual-machines/shadowbane-testing/diagnostics/vendor-1.8.2-8aad37f`.
The preparation script verifies staged hashes, refuses an existing destination,
checks space, prepares from the frozen baseline, verifies the resulting client
and installed wheel identity, and writes guest-local receipts. It does not stop
the running 1.8.1 client, launch another game, or change shortcuts. Preparation
completion and the eventual launch must be recorded separately.

Next: verify prepared runtime, restart/login into it, select Malik's random
Gilded Scepter recipe, inspect the fresh native receipt, then run one durable
fill-available-slots batch. Confirm every queue addition before any next command.
After that, finish completed-item assessment/Keep and qualify Junk separately.

Preparation initially stopped before client copying because the first bootstrap
manifest used the private fixture filename rather than `sb.exe`. The manifest
was re-authored from the exact frozen `sb.exe` (same reviewed executable hash)
as `bootstrap-1.8.2-sb.manifest.json`. The hash table above records this corrected
manifest. The first manifest and failure receipts remain as local evidence.
Resume checks that exact failure and requires the client destination to be absent.

Separate runtime preparation completed and verified at 2026-09-14T12:11:47Z.
Guest-local `prepare-status.json` reports `prepared_verified`, exact source
`8aad37f`, and `launched: false`. DLL file version 1.8.2.0 and package hash were
rechecked. `launch-reviewed.ps1` and `Launch-Vendor-Test.cmd` are staged in that
runtime; launching refuses any running sb.exe, preserves current Config settings
from the prior runtime, verifies the client again, then records the new process
lifetime and loaded DLL. They have not been executed. Existing shortcuts and the
running 1.8.1 client (PID 988, lifetime 134338345902905271) remain unchanged.
The immediate required user step is closing that game so the new DLL can load
on restart; the agent can then launch the prepared version for user login.

## Verified launch - September 14

After the owner closed the prior client, the prepared 1.8.2 client launched.
The matching 32-bit verifier confirmed the loaded full DLL against the package
hash above. Exact process identifiers and launch evidence remain guest-local.
An initial 64-bit module query exposed only WOW64 support modules; the game was
not restarted in response. The local launcher now uses the matching verifier.

A read-only INSPECT request timed out before the client entered the world;
no Create, Keep or Junk request was sent. Independent observation confirmed
the pre-world state. Vendor command qualification remains pending login and
recipe selection. A successful DLL load does not certify command execution.

Next: log in as Treehugger, open Malik's random Gilded Scepter recipe before
Create, verify fresh native inspection and current capacity, then run one
durable fill-slots batch. Existing desktop shortcuts remain unchanged pending
the live test. Automatic completed-item handling remains unfinished.

## First automatic batch verified

After login and recipe selection, native inspection returned ready with three
free slots. One durable batch filled all three. Each Create was sent once and
received a distinct correlated queue addition before the next request. An
independent owned-queue observation matched all three items as cooking.
Detailed batch evidence and runtime identifiers are excluded from published source.
No Keep or Junk has run. Completion assessment and automatic Keep are next;
full recurring rolling remains unfinished. The five-minute passive completion
observer detached normally without a completed result; a fresh independent read
still matched all three batch items as cooking. No observer remains active.
