#pragma once
#include "movement_lifetime.h"
#include "door_targeting.h"
#include "vendor_wire.h"
namespace wonderbane::extension::vendor_navigation {
// One owner-update transaction. Query output owns ArcObj references; selection
// consumes its argument. Faulted transactions quarantine uncertain ownership.
class BuildingTarget {
public:
    using Key = std::array<std::uint32_t, 2>;
    using Admission = bool (*)(void*) noexcept;
    BuildingTarget() = default;
    BuildingTarget(const BuildingTarget&) = delete;
    BuildingTarget& operator=(const BuildingTarget&) = delete;
    bool Bind(HWND) noexcept;
    vendor::wire::Outcome Open(const movement::NativeScene&, Key, Admission, void*) noexcept;
    bool Available() const noexcept { return base_ && !faulted_; }
private:
    struct Node { Node* next; Node* previous; void* object; };
    struct List { Node* sentinel = nullptr; };
    static_assert(sizeof(Node) == 12 && sizeof(List) == 4);
    struct Calls {
        List* (__thiscall* construct)(List*, const unsigned char*) = nullptr;
        void (__thiscall* query)(void*, const movement::GroundPoint*, const movement::GroundPoint*, List*) = nullptr;
        void (__thiscall* release)(void**, void*) = nullptr;
        void (__cdecl* pool_return)(void*, std::uint32_t) = nullptr;
        void (__cdecl* select)(void*) = nullptr;
        bool (__cdecl* dispatch)(const void*, void*) = nullptr;
    } calls_{};
    bool Owner() const noexcept;
    bool Current(const movement::NativeScene&, Admission, void*) const noexcept;
    bool Position(const movement::NativeScene&, movement::GroundPoint&) const noexcept;
    bool KeyOf(void*, Key&) const noexcept;
    bool Match(void*, Key) const noexcept;
    void Clear();
    vendor::wire::Outcome Run(const movement::NativeScene&, Key, Admission, void*);
    vendor::wire::Outcome RunCxx(const movement::NativeScene&, Key, Admission, void*) noexcept;
    vendor::wire::Outcome Guarded(const movement::NativeScene&, Key, Admission, void*) noexcept;
    std::uintptr_t base_ = 0;
    HWND window_ = nullptr;
    DWORD thread_ = 0;
    bool faulted_ = false, entered_ = false, running_ = false;
    List list_{};
    void* held_ = nullptr;
    friend struct BuildingTargetTestAccess;
};
}
