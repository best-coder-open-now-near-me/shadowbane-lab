#pragma once
#include "combat_activation_lifecycle.h"
#include <span>
namespace wonderbane::extension::combat::activation {
struct Handle {
    std::size_t slot=ActivationHistory::invalid;
    std::uint64_t ticket{};
    ActivationIdentity identity{};
    explicit operator bool() const noexcept { return slot<ActivationHistory::capacity&&ticket&&identity.Valid(); }
};
enum class Result { unknown, awaiting, active, completed, interrupted, relinquished };
// Reserved by the native retained journal, before one exact owned invocation.
Handle Arm(std::size_t,const ActivationIdentity&,std::uint32_t,ActivationOrigin) noexcept;
void RecordReturn(const Handle&,bool queued,bool owned_followup=false) noexcept;
Result Read(const Handle&) noexcept;
bool ResetExactLifetime(const ActivationIdentity& expected_old) noexcept;
// Transparent observation only; callers must always invoke native originals.
void ForeignItemSend(std::uintptr_t actor) noexcept;
void ForeignPowerUse(std::uintptr_t actor) noexcept;
void RecordManualPowerSend(std::uintptr_t actor,std::uint32_t power) noexcept;
ActivationHistory::Transition BeginOwnedFollowup(const Handle&) noexcept;
void OwnedFollowupReturned(const Handle&,const ActivationHistory::Transition&,bool normal_exact,bool state6) noexcept;
bool ObserveOrdinaryPower(std::uintptr_t original,std::uint32_t id,int rank,void* actor,void* target,
    const float* position,std::array<std::uint32_t,2> key);
void ObserveManualFollowup(std::uintptr_t original,void* actor,void* target,void* definition,int rank);
void OtherActivity(std::uintptr_t actor) noexcept;
// Existing power observer owns these callsite bytes. Returns a transparent
// wrapper with identical ABI, or original if no supported route was requested.
std::uintptr_t Route(std::uint32_t site,std::uintptr_t frame,std::uintptr_t original) noexcept;
bool Start(std::uintptr_t image) noexcept;
bool Ready() noexcept;
bool NormalizeOwnedCode(std::uintptr_t image,std::uint32_t text_rva,
    std::span<std::uint8_t> code,std::span<const std::uint8_t> disk) noexcept;
}
