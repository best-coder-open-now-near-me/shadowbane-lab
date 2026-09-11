# Remappable controller subset 1.8.0

Exact package source433dc819a7feaa7bececff2f3434a9b842e61539, integration branch
codex/native-lifecycle-hardening. Includes owner6521543 profile checkpoint and
d1b9238 review fix; root versionb727b0f. Previous installed/accepted source97612e6
remains running as1.7.8. Main unchanged. Door gameplay mission is tracked in
[door-interaction.md](door-interaction.md); doors and combat are NOT included here.

Supported actions: native movement vector, native camera vector, cancel movement/
navigation; editable stick/button/trigger and shoulder-modifier bindings, unbind,
restore defaults and atomic save/apply. No key synthesis, unverified action choices
or controller combat completion claim. Existing chat and parent-frame policies stay.

Compatibility decision: action header schema3, settings format2/104 bytes with
profile format1, old52-byte saved-preference migration. Old/new unsupported wire
messages reject before mutation. Diagnostic schema3 and extension ABI1.7.4 unchanged;
product1.8.0/wheel0.3.0 are distinct. Always use the matching wheel/DLL pair.

Independent source review approved exact433dc81, previous P2 closed: profile IPC
presence is mandatory and checked exactly once, including negative-result tests.
Failed and nested controller-cancel regressions are also mandatory. Review was
source inspection only, distinct from root execution below.

Private package root E:/Projects/shadowbane/artifacts/combined-packages/b487c18d.
- ZIP4001dc1cdcc12cd600cced9445c8173362e804d92431a1f72753701271b0eb67
- Full DLL7d1c528e5a48ac41ad083791280aa999087ccb6e69f9570aa6d97a33b4a88da5
- Diagnostics DLL272d37eb5f75273dbeca7fdb2edb715c3ca37230bf233d7c44703b95cbfa68cb
- Wheel b117722960e2d1ab74666c812bad05773f7eda26724fd365f976cc1a29c2f182

Exact builder passed1875 Python tests,14 skips,238 subtests,Ruff, both ALL_BUILD
profiles;135 executed required native suite passes per profile,three no-argument
binding skips, with actual cue/sky/prepared bindings separately executed/passed.
Each profile63 IPC/reader/profile tests+15 subtests passed,no skips; mandatory
profile configuration result independently checked. Installed wheel/panels/readers
passed outside checkout; additional remapped movement/camera/trigger+modifier cancel
codec roundtrip passed from installed wheel outside checkout. All58 receipt file
hashes/sizes and ZIP CRC passed. Known ideal-transparency findings remain deferred
and separate; artifact retains existing diagnostic-only classification.

CI34588685107 is pending final diagnostics-native job at this checkpoint. Do not
claim final CI completion yet. Root log artifacts/combined-1.8.0-reviewed-build.log;
all package logs/results/manifest beside artifact. Preliminary4153e9bd/b727b0f is
superseded, not the reviewed package. No VM installation or owner test requested.

Next: verify final CI actual execution, retain complete supported subset candidate,
and continue character-forward door implementation. A future profile live check
should exercise edit/save/reopen, a changed binding plus shoulder context, cancel,
and release/focus recovery; do not repeat broad accepted navigation or chat runs.
