#pragma once
#include "combat_power_observer.h"
namespace wonderbane::extension::combat::power {
// Owner-thread only, with actor/target retained by caller under its exact scene,
// Grant and target-authority lease. No selection or hotbar input is consulted.
// Caller wraps this faulting native frame in Boundary.Restore via __finally.
// Qualified object-target and explicit actor-target powers only; recipient mode
// is checked against the native definition before entry.
bool Invoke(Scope& scope);
}
