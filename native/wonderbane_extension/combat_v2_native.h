#pragma once
#include "combat_party.h"
#include "combat_initiation.h"

#include "combat_v2_controller.h"
#include "combat_target_policy.h"
#include "combat_power_entry.h"
#include "combat_submission.h"
#include "combat_melee_entry.h"

namespace wonderbane::extension::combat::v2 {
class NativeTarget final {
public:
    using Admission = bool (*)(void*) noexcept;
    struct Observation {
        std::uint32_t mode = 0, action = 0, animation_event_index = 0;
        std::uintptr_t target = 0;
        initiation::Snapshot initiation{};
        bool ClearInitiation() const noexcept { return initiation.Clear(); }
        bool operator==(const Observation&) const = default;
    };
    bool Bind(HWND) noexcept;
    bool Available() const noexcept { return base_ && !faulted_; }
    bool Prepared() const noexcept { return actor_ && target_ && Available(); }
    Operation Prepare(const movement::NativeScene&, const wire::Command&,
        Admission current, Admission append_current, void*) noexcept;
    Operation Execute(const wire::Command&) noexcept;
    bool Cancel(const movement::NativeScene&, Admission stop_current, void*, Observation&) noexcept;
    bool ReadState(const movement::NativeScene&, Observation&) const noexcept;
    bool CombatTargetCurrent() const noexcept;
    std::uintptr_t TargetAddress() const noexcept { return reinterpret_cast<std::uintptr_t>(target_); }
    // Release only references owned by this transaction. A fault quarantines them.
    bool Clear() noexcept;
    bool Current() noexcept;
private:
    struct Calls {
        void** (__thiscall* lookup)(void*, void**, const std::uint32_t*) = nullptr;
        void (__thiscall* retain)(void*, void**) = nullptr;
        void (__thiscall* release)(void**, void*) = nullptr;
        decltype(&melee::Invoke) attack = nullptr;
        decltype(&power::Invoke) cast = nullptr;
        decltype(&power::ReadSelfInitiation) self_initiation = nullptr;
        bool (__cdecl* dispatch)(const void*, void*) = nullptr;
    } calls_{};
    bool Owner() const noexcept;
    bool RawCurrent() const noexcept;
    bool Identity() const noexcept;
    bool Position(movement::GroundPoint&) const noexcept;
    bool Retain(void*&);
    void ClearImpl();
    bool ClearCxx() noexcept;
    bool ClearMessagesCxx() noexcept;
    Operation Run();
    Operation RunCxx() noexcept;
    Operation Guarded() noexcept;
    Operation PrepareImpl();
    bool CancelImpl(const movement::NativeScene&, Admission, void*, Observation&);
    bool CancelCxx(const movement::NativeScene&, Admission, void*, Observation&) noexcept;
    static bool Gate(void*) noexcept;
    static bool AppendGate(void*) noexcept;
    std::uintptr_t base_ = 0;
    HWND window_ = nullptr;
    DWORD thread_ = 0;
    bool faulted_ = false, running_ = false, dispatched_ = false, preparing_ = false;
    movement::NativeScene scene_{};
    wire::Command command_{};
    party::Snapshot party_{};
    submission::Receipt submission_receipt_{};
    power::Receipt power_receipt_{};
    // One positively observed request in this retained engagement. Never rebuilt
    // from a matching protocol ID or host receipt; cleared on entry/cleanup.
    std::uint32_t instant_self_id_{};
    std::uint64_t instant_self_epoch_{};
    std::uint64_t pre_entry_epoch_{};
    std::uint32_t pre_entry_self_id_{};
    power::InitiationDefinition instant_self_definition_{};
    const char* stage_ = "none";
    Admission current_ = nullptr, append_current_ = nullptr;
    void* context_ = nullptr;
    void* actor_ = nullptr;
    void* target_ = nullptr;
    void* request_ = nullptr;
    void* transfer_ = nullptr;
    friend struct NativeTargetTestAccess;
};
}
