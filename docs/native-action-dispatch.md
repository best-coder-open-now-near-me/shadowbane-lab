# Native client action actuator

The production `/pve` actuator belongs inside the injected WonderBane extension. Desktop input
remains a deprecated bootstrap and validation path; it is not the native automation architecture.

## Boundary

```text
PvE policy
  -> semantic action key
  -> NativeExtensionPvEIntentDispatcher
  -> versioned host-to-client command ring
  -> wonderbane-extension.dll
  -> reviewed client-thread dispatcher
  -> ordinary Shadowbane client/server action lifecycle
```

The native path does not call PyAutoGUI, synthesize keys, switch hotbars, post window messages, or
click the screen. The server remains authoritative over whether an action is legal.

## Transport ABI

The extension now creates a separate command mapping and two auto-reset signals for each exact
client process identity:

```text
Local\ShadowbaneLab.Extension.Actions.<pid>.<creation-filetime>
Local\ShadowbaneLab.Extension.ActionCommand.<pid>.<creation-filetime>
Local\ShadowbaneLab.Extension.ActionResult.<pid>.<creation-filetime>
```

The mapping contains independent bounded command and result rings. Both rings use committed
sequences, exact geometry/version checks, the client PID plus process-creation FILETIME, a
single-host heartbeat lease, deadlines based on the same-machine tick counter, fixed ASCII payload
capacities, and explicit result stages:

```text
received
resolved
submitted_to_client
rejected_by_client
action_queue_observed
effect_observed
failed
```

Receipt is not treated as native submission. The host adapter reports success only at
`submitted_to_client`, `action_queue_observed`, or `effect_observed`.

## Initial semantic mappings

The host-side native dispatcher preserves the known native identifiers instead of compiling them
back into keys:

| Semantic action | Native request |
| --- | --- |
| `client.pve.target_next_mobile` | Arcane action `(188, 0, 0, "")` |
| `client.pve.target_previous_mobile` | Arcane action `(189, 0, 0, "")` |
| `shadowbane.basic_attack` | captured Arcane action `(1551, 0, 0, "")` |
| `shadowbane.assassin.shadow_touch` | learned power `ASS-013` |

Action `48` and its string argument remain representable by the generic tuple codec; it is not yet
exposed as a semantic mapping because its individual meanings must remain explicit.

## Current activation state

The checked-in extension advertises **transport capability only**. Its rejection worker validates
and drains commands so host-to-client IPC, backpressure, process identity, deadlines, and result
handling can be exercised now, but it never calls a Shadowbane method. Valid commands currently
finish with:

```text
failed / ERROR_NOT_SUPPORTED / reviewed_client_dispatcher_unavailable
```

This is intentional. No receiver pointer, calling convention, context object, or execution-thread
claim is invented.

## Next calibration

1. Hook the ordinary UI submission of action `188` and capture the receiver, registers, stack,
   calling convention, and thread identity.
2. Replay `188` from that exact in-client execution context, then validate `189`, `182`, `102`, and
   `1551`.
3. Hook the real F2 `PowerHotButtonInfo` execution for `ASS-013`; recover learned-power lookup,
   selected-target dependency, rank/context data, and required thread.
4. Replace the rejection-only dispatch seam with reviewed build-pinned profiles.
5. Validate passively and plan-only before routing live `/pve` through the native actuator.

Until those steps pass, the native dispatcher fails closed and the current live launcher is not
silently switched to it.
