# Native text ownership after closing input

The .95 travel attempt was rejected before acquiring a movement grant. Native
change-history showed UI/text ownership throughout that interval. The user then
clarified that Who search had already been closed; the flag was not evidence
that the user still had an interface open.

Stable passive reads on the exact reviewed .17 client showed native text entry
disabled, neutral modal/drag/inhibit/gesture fields, and a retained kind-5 focused
control. Exact-image RTTI identifies the containing ArcChannelHud and confirms
the zero-adjustment ArcHud getter result. The native text predicate first checks
its enable global; our additional focused-control fallback ignored that check.
This was a false positive in our guard, affecting both movement and upkeep.

The correction rereads the native enable state after the native predicate and
only applies the conservative focused-kind fallback while text is enabled.
The native predicate's positive result still inhibits. Complete gates are read
twice; closing during a query may conservatively inhibit that snapshot but does
not latch later snapshots. Unreadable state, modal input, item drag, active text
and scene changes retain their existing fail-closed behavior. No focus bypass,
UI mutation, native input injection or timing change is introduced.

The existing exact file hash and entire relocated loaded-text verification seal
the native predicate and its global operand. Tests cover close with retained
focus, re-enable during the predicate, close during focus lookup, unreadable
state and recovery, alongside existing active-text/modal/drag cases. Full and
diagnostics-only native UI fixtures pass. Qualified deployment and live movement
and upkeep validation remain pending; the source fix alone makes no such claim.
