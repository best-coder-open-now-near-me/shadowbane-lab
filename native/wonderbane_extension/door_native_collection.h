#pragma once
#include "door_targeting.h"
#include "movement_lifetime.h"
#include <array>
#include <cstddef>
namespace wonderbane::extension::movement {
// Owner-update scratch only. Native references never enter a renderer snapshot.
// Explicit Clear belongs to the same admitted owner phase. Unexpected native
// exceptions quarantine uncertain references instead of retrying their release.
class NativeDoorCollection {
public:
    struct Door {
        void* object = nullptr;
        void* structure = nullptr; // borrowed from structures_ for this phase
        DoorIdentity identity{};
    };
    bool Bind(HWND client_window) noexcept;
    bool Acquire(const NativeScene&, GroundPoint origin) noexcept;
    bool Clear() noexcept;
    std::size_t Size() const noexcept { return valid_ ? door_count_ : 0; }
    const Door& At(std::size_t i) const noexcept { return doors_[i]; }
    std::uint64_t Generation() const noexcept { return valid_ ? generation_ : 0; }
    bool Available() const noexcept { return base_ && !faulted_; }
private:
    struct Node { Node* next; Node* previous; void* object; };
    struct List { Node* sentinel = nullptr; };
    static_assert(sizeof(Node) == 12 && sizeof(List) == 4);
    struct Calls {
        List* (__thiscall* construct)(List*, const unsigned char*) = nullptr;
        void (__thiscall* query)(void*, const GroundPoint*, const GroundPoint*, List*) = nullptr;
        void (__thiscall* retain)(void**) = nullptr;
        void (__thiscall* release)(void**, void*) = nullptr;
        void (__cdecl* pool_return)(void*, std::uint32_t) = nullptr;
    } calls_{};
    bool Owner() const noexcept;
    bool RunAcquire(const NativeScene&, GroundPoint);
    bool ReadDoors(const NativeScene&);
    bool ReadDoorsGuarded(const NativeScene&);
    bool AcquireCxx(const NativeScene&, GroundPoint) noexcept;
    bool AcquireGuarded(const NativeScene&, GroundPoint) noexcept;
    void RunClear();
    bool ClearCxx() noexcept;
    bool ClearGuarded() noexcept;
    void ClearList();
    std::uintptr_t base_ = 0;
    HWND window_ = nullptr;
    DWORD thread_ = 0;
    bool faulted_ = false, valid_ = false;
    std::uint64_t generation_ = 0;
    List list_{};
    DoorCollectionAdmission::ReadLease lease_{};
    std::array<void*, 128> structures_{};
    std::array<Door, 256> doors_{};
    std::size_t structure_count_ = 0, door_count_ = 0;
    friend struct NativeDoorCollectionTestAccess;
};
}
