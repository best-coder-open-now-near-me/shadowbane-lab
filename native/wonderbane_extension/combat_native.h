#pragma once
#include "combat_party.h"
#include "combat_diagnostic.h"
#include "combat_wire.h"
#include "combat_submission.h"

namespace wonderbane::extension::combat {
class NativeTarget final {
public:
    using Admission = bool (*)(void*) noexcept;
    struct State { std::uint32_t mode = 0, action = 0; bool target = false; };
    struct Result { wire::Outcome outcome = wire::Outcome::unavailable; bool queued = false; Diagnostic diagnostic{}; };
    bool Bind(HWND) noexcept;
    bool Available() const noexcept { return base_ && !faulted_; }
    Result Attack(const movement::NativeScene&, const wire::Command&,
                  Admission current, Admission enter, Admission append_current, void*) noexcept;
    bool Cancel(const movement::NativeScene&, Admission stop_current, void*, State&) noexcept;
    bool ReadState(const movement::NativeScene&, State&) const noexcept;
    bool CombatTargetCurrent() const noexcept;
    // Release only references owned by this transaction. A fault quarantines them.
    bool Clear() noexcept;
    bool Current() noexcept;
private:
    struct Calls {
        void** (__thiscall* lookup)(void*, void**, const std::uint32_t*) = nullptr;
        void (__thiscall* retain)(void*, void**) = nullptr;
        void (__thiscall* release)(void**, void*) = nullptr;
        void (__cdecl* select)(void*) = nullptr;
        bool (__cdecl* dispatch)(const void*, void*) = nullptr;
    } calls_{};
    bool Owner() const noexcept;
    bool RawCurrent(bool selected) const noexcept;
    bool Identity() const noexcept;
    bool Position(movement::GroundPoint&) const noexcept;
    bool Retain(void*&);
    void ClearImpl();
    bool ClearCxx() noexcept;
    Result Run();
    Result RunCxx() noexcept;
    Result Guarded() noexcept;
    bool CancelImpl(const movement::NativeScene&, Admission, void*, State&);
    bool CancelCxx(const movement::NativeScene&, Admission, void*, State&) noexcept;
    static bool Gate(void*) noexcept;
    static bool AppendGate(void*) noexcept;
    std::uintptr_t base_ = 0;
    HWND window_ = nullptr;
    DWORD thread_ = 0;
    bool faulted_ = false, running_ = false, selected_ = false, dispatched_ = false;
    movement::NativeScene scene_{};
    wire::Command command_{};
    party::Snapshot party_{};
    submission::Receipt submission_receipt_{};
    Stage stage_ = Stage::none;
    Admission current_ = nullptr, enter_ = nullptr, append_current_ = nullptr;
    void* context_ = nullptr;
    void* actor_ = nullptr;
    void* target_ = nullptr;
    void* selection_argument_ = nullptr;
    friend struct NativeTargetTestAccess;
};
}
