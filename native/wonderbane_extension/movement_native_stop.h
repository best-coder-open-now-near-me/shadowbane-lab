#pragma once
#include <Windows.h>
#include "movement_controls.h"
#include "movement_lifetime.h"
#include <array>
#include <cstdint>
namespace wonderbane::extension::movement {
// This executor has no movement ownership of its own. Controls remains the only
// authority; every native callback boundary rechecks the captured grant and actor.
class NativeStop {
public:
    explicit NativeStop(const Controls& controls) noexcept : controls_(controls) {}
    bool Bind(HWND client_window) noexcept;
    // Normal movement/camera phase belongs to the verified native-update hook.
    // The verified HWND callback may enter only the explicit emergency-stop
    // phase below; polling/render/foreign teardown threads cannot actuate.
    bool BeginUpdate(void* native_window) noexcept;
    bool BeginUpdate(void* native_window, const NativeScene&) noexcept;
    bool BeginOwnerStop(HWND source_window, void* native_window, const NativeScene&) noexcept;
    void EndUpdate() noexcept;
    bool Execute(const Grant&) noexcept;
    // Camera input does not acquire or retire movement ownership.
    bool RotateCamera(Vector2 radians) noexcept;
    bool CameraBasis(Vector2& forward, Vector2& right) noexcept;
    // Direction is normalized X/Z in the player's native parent-local frame.
    // tick_ms comes from the owning update's monotonic clock, never render dt.
    bool Steer(const Grant&, Vector2 direction, std::uint64_t tick_ms, bool start) noexcept;
    // Uses native unprojection, world collision and parent-local hit conversion.
    // Retained hit references belong only to this admitted update, until EndUpdate.
    bool PickGround(int client_x, int client_y, GroundPoint&) noexcept;
    bool MoveToPick(const Grant&, GroundPoint) noexcept;
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
    struct Ray {
        void* actor; GroundPoint origin; GroundPoint direction; std::uint32_t flags;
        float distance; void* parent; void* face;
    };
    static_assert(sizeof(Ray) == 44);
    struct GroundTarget { GroundPoint point; void* actor; void* parent; };
    static_assert(sizeof(GroundTarget) == 20);
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
        GroundPoint* (__cdecl* unproject)(GroundPoint*, int, int, float) = nullptr;
        Ray* (__thiscall* ray)(Ray*, void*, const GroundPoint*, const GroundPoint*, bool) = nullptr;
        bool (__thiscall* ray_cast)(void*, Ray*) = nullptr;
        GroundPoint* (__thiscall* ray_point)(Ray*, GroundPoint*) = nullptr;
        void (__thiscall* release_parent)(void**, void*) = nullptr;
        void (__thiscall* apply_ray)(Ray*, void*, bool) = nullptr;
        void* (__thiscall* parent)(void*) = nullptr;
        GroundTarget* (__thiscall* ground_with_refs)(GroundTarget*, GroundPoint, void*, void*) = nullptr;
        void (__thiscall* release_ground_actor)(void**, void*) = nullptr;
        GroundTarget* (__thiscall* ground_target)(GroundTarget*, GroundPoint) = nullptr;
        void** (__thiscall* move)(void*, void**, const GroundTarget*, bool, bool, bool, bool*, bool) = nullptr;
        void (__thiscall* camera)(void*, float, float, float, bool) = nullptr;
    } calls_{};
    struct Target {
        Grant grant{};
        std::uintptr_t actor = 0, world = 0, window = 0, request = 0, parent = 0;
        Identity identity{};
    } target_{};
    bool Capture(const Grant&) noexcept;
    bool SceneCurrent(const Target&) const noexcept;
    bool Current(const Target&) const noexcept;
    bool ClearPickCxxGuarded() noexcept;
    bool ClearPickGuarded() noexcept;
    bool PickCxxGuarded(int, int, GroundPoint&) noexcept;
    bool PickGuarded(int, int, GroundPoint&) noexcept;
    bool RunPick(int, int, GroundPoint&);
    bool RunBasis(Vector2&, Vector2&);
    bool BasisCxxGuarded(Vector2&, Vector2&) noexcept;
    bool BasisGuarded(Vector2&, Vector2&) noexcept;
    bool RunPickMove(const Target&);
    bool PickMoveCxxGuarded(const Target&) noexcept;
    bool PickMoveGuarded(const Target&) noexcept;
    bool RequestCurrent(const Target&) const noexcept;
    bool MovementCurrent(const Target&) const noexcept;
    bool RunSteer(const Target&, Vector2, std::uint64_t, bool);
    bool SteerCxxGuarded(const Target&, Vector2, std::uint64_t, bool) noexcept;
    bool SteerGuarded(const Target&, Vector2, std::uint64_t, bool) noexcept;
    bool RotateCameraGuarded(const Target&, Vector2) noexcept;
    bool Run(const Target&);
    bool RunCxxGuarded(const Target&) noexcept;
    bool RunGuarded(const Target&) noexcept;
    bool CancelQueued(const Target&);
    void ReleaseMessage();
    const Controls& controls_;
    std::uintptr_t base_ = 0;
    HWND window_ = nullptr;
    DWORD thread_ = 0;
    NativeScene lifetime_scene_{};
    bool require_lifetime_ = false, stop_only_ = false;
    bool bound_ = false, faulted_ = false, executing_ = false, captured_ = false, in_update_ = false;
    // On an unexpected native exception, retain ambiguous resources and fail
    // closed. Never retry an uncertain send or unload code from under callbacks.
    void* held_actor_ = nullptr;
    void* message_ = nullptr;
    void* held_marker_ = nullptr;
    GroundTarget ground_{};
    bool ground_owned_ = false;
    GroundPoint drag_point_{};
    bool drag_submitted_ = false, drag_deferred_ = false;
    Ray ray_{};
    Target pick_target_{};
    GroundPoint pick_point_{};
    bool ray_owned_ = false, pick_valid_ = false;
    Target steering_target_{};
    Vector2 steering_direction_{};
    std::uint64_t steering_tick_ = 0, steering_sent_tick_ = 0;
    bool steering_captured_ = false, steering_submitted_ = false, steering_sent_ = false, steering_deferred_ = false;
    friend struct NativeStopTestAccess;
};
}
