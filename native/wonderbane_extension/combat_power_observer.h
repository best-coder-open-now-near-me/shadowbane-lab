#pragma once
#include "combat_submission.h"
#include "combat_activation_observer.h"
#include "combat_power_readiness.h"
#include "combat_power_local.h"
#include <array>
#include <cstdint>
#include <span>
namespace wonderbane::extension::combat::power {
using Key = std::array<std::uint32_t, 2>;
enum class TargetMode { engagement_object, self };
enum class Authority { engagement, actor };
enum class Result { denied, entered, queued, uncertain };
struct Receipt {
    Result result = Result::denied;
    bool native_entered = false, send_observed = false, append_observed = false;
    bool followup_entered = false;
    std::uint64_t initiation_epoch = 0;
    std::uint64_t local_initiation_token = 0;
    Availability availability = Availability::unknown;
    std::uint64_t availability_epoch = 0;
    // Optional copied diagnostics only. Never used for admission or settlement.
    struct Observation {
        bool definition_known{}, state_known{}, use_called{}, use_returned{}, use_value{};
        std::uint32_t required_mode{}, actor_mode{}, state_aux{}, initiation_state{}, definition_flags{};
    } observation{};
};
struct Context {
    std::uintptr_t image{}, actor{}, target{}, writer{}, container{};
    Key actor_key{}, target_key{};
    std::uint32_t power_id{};
    bool (*current)(void*) noexcept = nullptr;
    // Queue-lock-safe scalar/atomic observations only. No callbacks into native code.
    bool (*append_current)(void*) noexcept = nullptr;
    void* owner = nullptr;
    // Stable owner storage; must outlive Scope and the enclosing SEH boundary.
    Receipt* receipt = nullptr;
    // Engagement authority retains its object even for a self recipient.
    // Actor authority has no target object and permits only the self recipient.
    TargetMode target_mode = TargetMode::engagement_object;
    Authority authority = Authority::engagement;
    activation::Handle activation{};
    std::uintptr_t Recipient() const noexcept { return target_mode == TargetMode::self ? actor : target; }
    const Key& RecipientKey() const noexcept { return target_mode == TargetMode::self ? actor_key : target_key; }
};
namespace detail { struct Observer; struct Entry; }
class Scope final {
public:
    explicit Scope(const Context&) noexcept;
    ~Scope();
    Scope(const Scope&) = delete;
    Scope& operator=(const Scope&) = delete;
    // Called after learned-rank/category qualification and before mutating native entry.
    bool CanEnter() const noexcept;
    // Same binding/current gate after an admitted native prerequisite. This does
    // not provide the private bridge frame required by sender/append observers.
    bool Current() const noexcept;
    bool Enter(std::uintptr_t definition, std::uint32_t native_rank) noexcept;
    bool AdmitAvailability(Availability value, std::uint64_t epoch) noexcept;
    Receipt Finish() noexcept;
    const Context& Binding() const noexcept { return context_; }
private:
    friend struct detail::Observer;
    friend struct detail::Entry;
    void PublishObservation() noexcept;
    Context context_{};
    Receipt receipt_{};
    Scope* previous_{};
    std::uintptr_t definition_{}, ticket_{};
    std::uintptr_t native_frame_{}, native_return_{};
    std::uint32_t rank_{};
    std::uint64_t preparation_epoch_{};
    bool active_ = false, blocked_ = false, send_seen_ = false, append_seen_ = false;
};
class Boundary final {
public:
    Boundary() noexcept;
    void Restore() noexcept;
private:
    Scope* previous_{};
};
// Process-pinned exact callsite hooks. Never unload while native code can call them.
bool Start(std::uintptr_t image) noexcept;
bool Ready() noexcept;
// Zero means unavailable/exhausted. Any observed native protocol mutation or
// power preparation invalidates earlier epochs, including foreign actors.
std::uint64_t InitiationEpoch() noexcept;
bool NativeUseInFlight() noexcept;
LocalInitiationState ReadLocalInitiation(std::uint64_t token,std::uintptr_t actor,const Key&,std::uint32_t power) noexcept;
bool NormalizeOwnedCode(std::uintptr_t image, std::uint32_t text_rva,
    std::span<std::uint8_t> code, std::span<const std::uint8_t> disk) noexcept;
}
