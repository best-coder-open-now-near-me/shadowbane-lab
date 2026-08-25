# ADR 0001: Use one semantic protocol across simulation and deployment

- **Status:** Accepted
- **Date:** 2026-08-25

## Context

Policies must train in a fast deterministic playground and later act through either the
Shadowbane emulator or a real client. Encoding simulator opcodes, server tokens, hotbar
slots, or screen coordinates directly in policy outputs would create separate policy
interfaces and make training behavior diverge from deployment behavior.

## Decision

All policies communicate using the versioned sequence:

```text
Observation -> Affordances -> Decision -> Events
```

The policy selects a bound semantic affordance. Adapters translate that decision to their
own execution mechanism and normalize the result back into causal events.

The client-input adapter owns calibration and mappings such as semantic action to hotbar
slot and observed entity to client-relative screen position. The policy and simulator do
not receive these mappings.

## Consequences

- Policies can be replayed across simulator, server, recording, dry-run, and client-input
  adapters.
- Differential validation can correlate one decision with both simulated and authoritative
  outcomes.
- UI layout or power-token changes require adapter or ruleset updates, not retraining solely
  because an identifier changed.
- Affordance generation becomes a critical trusted boundary and must fail closed when state
  or calibration is stale.
