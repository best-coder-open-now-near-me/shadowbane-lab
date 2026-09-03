Shadowbane Druid PvE AoE macro

Power shortcuts expected in the game:
  F1  Call Lightning (first power in the center loop)
  F2  Earthquake (second power in the center loop)
  F3  Hedge of Thorns (reapply no sooner than every 40 seconds)
  F4  Long-duration buff (reapply every 600 seconds)
  F5  Defensive Stance (reapply every 600 seconds)
  F6  Concoction potion (reuse every 6000 seconds)
  C   Enter combat mode once before the first Defensive Stance

Macro shortcuts:
  F8   Toggle continuous rotation
  F9   Run one rotation
  F10  Stop the macro process

The macro uses End for Target Self. It resets selection to self before every
due maintenance action and at the beginning of every AoE cycle; it never
invokes Target Next Mob. Due maintenance is handled only between complete
AoE cycles.

The center loop self-targets, casts F1 Call Lightning, then casts F2
Earthquake and leaves a long post-cast recovery for a cycle of about 15.6
seconds. F3 Hedge of Thorns refreshes on its separate 40-second due timer
between complete center-loop cycles. Keys are sent only while an sb.exe
Shadowbane window is the active foreground process. The macro pauses on
focus loss.

C is a stateful combat-mode toggle. The macro presses it exactly once per
runner process, immediately before the first F5 Defensive Stance, and assumes
the character begins that process out of combat mode. Later F5 refreshes do
not toggle C again.

On the first run, preparation is completed before any offensive power:
F4 buff, C combat mode, F5 Defensive Stance, then F6 Concoction. Only after
that setup does the macro cast F3 Hedge of Thorns and enter the F1/F2 loop.

Each run writes a timestamped log under:
  %LOCALAPPDATA%\ShadowbaneLab\macros

If a fatal error occurs, the PowerShell window remains open and shows the
log path until Enter is pressed.
