#pragma once
#include "combat_submission.h"
#include "combat_activation_observer.h"
#include <array>
#include <cstdint>
#include <span>
namespace wonderbane::extension::combat::item {
using Key = std::array<std::uint32_t, 2>;
enum class Result { denied, queued, uncertain };
struct Receipt {
    Result result = Result::denied;
    bool native_entered = false;
    bool send_observed = false;
    bool append_observed = false;
    bool ownership_quarantined = false;
};
// One immutable action owns this storage. It MUST outlive Invoke. No destructor:
// a faulting native output/release can leave ownership unknowable, so quarantine
// must never be retried, freed, or reused by a later request.
struct State {
    void* retained_item = nullptr;
    void* membership_item = nullptr;
    bool attempted = false;
    bool quarantined = false;
};
struct Context {
    std::uintptr_t image{}, actor{}, writer{}, container{}, item_address{}, template_address{};
    Key actor_key{}, item_key{}, template_key{};
    std::uint32_t template_type{}, template_flags{};
    // Actor is retained by the caller. This checks exact scene/Grant/actor fence.
    bool (*current)(void*) noexcept = nullptr;
    // Under queue lock: scalar/atomic observations only, no locks/native calls.
    bool (*append_current)(void*) noexcept = nullptr;
    void* owner = nullptr;
    activation::Handle activation{};
};
// Owner-thread only. No target, selection, power invocation or StopActive.
// Owns its C++/SEH boundary and restores TLS even if native frames are abandoned.
// Positive queue history is local transport evidence, never effect completion.
Receipt Invoke(const Context&, State&, Receipt& persistent_receipt) noexcept;
bool Start(std::uintptr_t image) noexcept;
bool Ready() noexcept;
bool NormalizeOwnedCode(std::uintptr_t image, std::uint32_t text_rva,
    std::span<std::uint8_t> code, std::span<const std::uint8_t> disk) noexcept;
}
