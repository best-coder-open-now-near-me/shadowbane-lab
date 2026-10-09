#pragma once
#include "combat_power_observer.h"
namespace wonderbane::extension::combat::power {
// Owner-thread only, with actor/target retained by caller under its exact scene,
// Grant and target-authority lease. No selection or hotbar input is consulted.
// Caller wraps this faulting native frame in Boundary.Restore via __finally.
// Qualified object-target and explicit actor-target powers only; recipient mode
// is checked against the native definition before entry.
struct InitiationDefinition {
    std::uintptr_t definition{};
    std::uint32_t rank{};
    double seconds{};
    bool operator==(const InitiationDefinition&) const = default;
};
// Read the current learned actor-target definition and ranked native INITTIME.
// May fault like Invoke; caller must use the same quarantining native boundary.
bool ReadSelfInitiation(std::uintptr_t image, std::uintptr_t actor, std::uint32_t power_id,
    InitiationDefinition& out);
bool Invoke(Scope& scope);
bool InvokeTrack(Scope& scope);
}
