#pragma once
#include <Windows.h>
#include "movement_controls.h"
#include <array>
#include <cstdint>
namespace wonderbane::extension::movement {
// This executor has no movement ownership of its own. Controls remains the only
// authority; every native callback boundary rechecks the captured grant and actor.
class NativeStop {
public:
    explicit NativeStop(const Controls& controls) noexcept : controls_(controls) {}
    bool Bind(HWND client_window) noexcept;
    // Enter/leave only around the verified native-update hook, before calling its
    // original. Input, render and teardown callbacks cannot execute native stop.
    bool BeginUpdate(void* native_window) noexcept;
    void EndUpdate() noexcept;
    bool Execute(const Grant&) noexcept;
    void SceneRetired(std::uint64_t scene) noexcept;
    bool Available() const noexcept { return bound_ && !faulted_; }
private:
    using Identity = std::array<std::uint32_t, 2>;
    struct Node {
        std::uint32_t color; Node* parent; Node* left; Node* right;
        Identity identity; std::array<std::uint32_t, 4> value;
    };
    static_assert(sizeof(Node) == 40);
    struct Map { Node* sentinel; std::uint32_t size; };
    struct Vector { void* begin; void* end; void* capacity; };
    struct Calls {
        void** (__thiscall* retain)(void**, void*) = nullptr;
        void (__thiscall* release)(void**) = nullptr;
        void (__thiscall* clear_actions)(void*, const Identity*) = nullptr;
        Node** (__thiscall* find)(void*, Node**, const Identity*) = nullptr;
        Node* (__cdecl* detach)(Node*, Node**, Node**, Node**) = nullptr;
        void (__thiscall* destroy_identity)(Identity*) = nullptr;
        void (__cdecl* pool_return)(void*, std::uint32_t) = nullptr;
        void* (__thiscall* erase_path)(void*, void*, void*) = nullptr;
        void (__thiscall* clear_continuation)(void*) = nullptr;
        GroundPoint* (__thiscall* position)(void*, GroundPoint*) = nullptr;
        void (__thiscall* destination)(void*, const GroundPoint*) = nullptr;
        void (__thiscall* clear_waypoint)(void*, std::uint32_t, std::uint32_t) = nullptr;
        void** (__thiscall* state)(void*, void**, bool, std::uint32_t, bool) = nullptr;
        void (__thiscall* send)(void*, void*) = nullptr;
    } calls_{};
    struct Target {
        Grant grant{};
        std::uintptr_t actor = 0, world = 0, window = 0, request = 0;
        Identity identity{};
    } target_{};
    bool Capture(const Grant&) noexcept;
    bool Current(const Target&) const noexcept;
    bool RequestCurrent(const Target&) const noexcept;
    bool Run(const Target&);
    bool RunCxxGuarded(const Target&) noexcept;
    bool RunGuarded(const Target&) noexcept;
    bool CancelQueued(const Target&);
    void ReleaseMessage();
    const Controls& controls_;
    std::uintptr_t base_ = 0;
    HWND window_ = nullptr;
    DWORD thread_ = 0;
    bool bound_ = false, faulted_ = false, executing_ = false, captured_ = false, in_update_ = false;
    // On an unexpected native exception, retain ambiguous resources and fail
    // closed. Never retry an uncertain send or unload code from under callbacks.
    void* held_actor_ = nullptr;
    void* message_ = nullptr;
    friend struct NativeStopTestAccess;
};
}
