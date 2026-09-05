#pragma once

#include <array>
#include <cstdint>
#include <optional>

namespace wonderbane::extension::movement {

struct Vector2 { float x = 0; float y = 0; };
struct GroundPoint { float x = 0; float y = 0; float z = 0; };
struct Token {
    std::array<char, 96> worker{};
    std::array<char, 96> operation{};
    bool operator==(const Token&) const = default;
};
enum class Owner : std::uint8_t { none, automation, manual };
struct Grant {
    std::uint64_t generation = 0;
    std::uint64_t scene = 0;
    Owner owner = Owner::none;
    Token token{};
    bool operator==(const Grant&) const = default;
};
enum class StopReason : std::uint8_t {
    release, takeover, focus, ui, disabled, device_lost, capture_lost,
    scene_changed, stalled, shutdown, binding_failure
};
enum class Result : std::uint8_t {
    accepted, stale, unavailable, inhibited, stop_failed, invalid
};
struct Settings {
    bool enabled = false;
    bool keyboard = true;
    bool controller = false;
    bool drag = true;
    // Win32 virtual-key codes: forward, backward, left, right.
    std::array<std::uint16_t, 4> keys{0x57, 0x53, 0x41, 0x44};
    // Explicit XInput slot, never the first connected controller.
    std::uint32_t controller_slot = 0;
    float movement_dead_zone = 0.20F;
    float camera_dead_zone = 0.15F;
    float camera_radians_per_second = 2.0F;
    bool invert_camera_x = false;
    bool invert_camera_y = false;
    // XBUTTON1 avoids reserving selection or the native right-drag camera gesture.
    std::uint16_t drag_button = 0x05;
    float drag_threshold_pixels = 6.0F;
};
bool ValidSettings(const Settings&) noexcept;
Vector2 RadialDirection(Vector2 value, float dead_zone) noexcept;
Vector2 RadialCamera(Vector2 value, float dead_zone) noexcept;

struct DragPress { float x = 0; float y = 0; bool ground_valid = false; };
struct Input {
    std::uint64_t tick_ms = 0;
    // A new character/scene or native parent coordinate frame needs a new nonzero identity,
    // even if an actor pointer is reused.
    std::uint64_t scene = 0;
    bool native_available = false;
    bool exact_foreground = false;
    bool ui_owns_input = false;
    std::array<bool, 256> keys{};
    bool controller_connected = false;
    std::uint32_t controller_slot = 0;
    Vector2 left_stick{};
    Vector2 right_stick{};
    bool camera_blocked = false;
    bool camera_basis_valid = false;
    Vector2 camera_forward{};
    Vector2 camera_right{};
    bool pointer_in_world = false;
    bool capture_valid = false;
    std::optional<DragPress> press_origin;
    float pointer_x = 0;
    float pointer_y = 0;
    bool ground_valid = false;
    GroundPoint ground{};
};

// Implemented only by the verified native adapter. Every method runs synchronously
// on the owning client thread. No callback may enqueue an untagged delayed write.
// Stop must cancel native pending movement, not merely stop supplying destinations.
// A takeover stop also retires native click/combat-follow intent even if no move
// has been recorded here. It must not restore that intent on manual release.
// SceneRetired must discard work for that scene without touching its replacement.
class NativeActuator {
public:
    virtual ~NativeActuator() = default;
    virtual bool Stop(const Grant&, StopReason) noexcept = 0;
    virtual bool Direction(const Grant&, Vector2, bool start) noexcept = 0;
    virtual bool Destination(const Grant&, GroundPoint, bool start) noexcept = 0;
    virtual bool Camera(Vector2 radians) noexcept = 0;
    virtual void Revoked(const Grant&, const Grant&, StopReason) noexcept = 0;
    virtual void SceneRetired(std::uint64_t) noexcept = 0;
    // A safety event nested inside this input/command's native callback can
    // veto its remaining work before a replacement grant or move is accepted.
    virtual std::optional<StopReason> Interrupted() const noexcept { return std::nullopt; }
};

// Exactly one instance per injected client. All calls (including automation
// dequeue and shutdown) are made on the verified owning thread, never a poller.
class Controls {
public:
    explicit Controls(NativeActuator& actuator) noexcept : actuator_(actuator) {}
    Result Configure(const Settings&) noexcept;
    void Tick(const Input&) noexcept;
    // Runtime calls this with a verified lifetime before read-only native picks.
    // It retires old authority without issuing a stop against the new actor.
    void ObserveScene(std::uint64_t) noexcept;
    Result AcquireAutomation(std::uint64_t expected_generation, Token, Grant&) noexcept;
    Result AutomationDestination(const Grant&, GroundPoint) noexcept;
    Result PauseAutomation(const Grant&) noexcept;
    Result Stop(const Grant&, StopReason = StopReason::release) noexcept;
    // Exact-owner safety command from the verified window thread. The runtime
    // defers a nested command until native actuation returns, then revalidates.
    Result EmergencyStop(const Grant&, StopReason) noexcept;
    void Shutdown() noexcept;
    bool ConsumesKey(std::uint16_t key) const noexcept;
    // Native event capture separately verifies current foreground/UI/lifetime;
    // capture need not wait for a sampling tick after enabling or restoring focus.
    bool CapturesKey(std::uint16_t key) const noexcept;
    bool ConsumesDrag() const noexcept { return drag_active_; }
    Grant Current() const noexcept { return grant_; }
    bool Ready() const noexcept { return available_ && !pending_stop_; }
    bool CameraReady() const noexcept { return available_ && !camera_faulted_; }
    // The native adapter checks this again at each callback boundary. A retained
    // failed stop is permitted only while the policy still excludes a new writer.
    bool AuthorizesNativeStop(const Grant& grant) const noexcept {
        return grant.scene != 0 && (grant == grant_ || (pending_stop_ && grant == pending_grant_));
    }
private:
    bool Retire(StopReason, Owner next, Token = {}, std::optional<std::uint64_t> next_scene = std::nullopt) noexcept;
    bool StopActive(StopReason) noexcept;
    void Inhibit(StopReason) noexcept;
    bool RetryStop() noexcept;
    bool ContinueInput() noexcept;
    NativeActuator& actuator_;
    Settings settings_{};
    Grant grant_{1, 0, Owner::none, {}};
    Grant pending_grant_{};
    StopReason pending_reason_ = StopReason::release;
    bool pending_stop_ = false;
    bool actuating_ = false;
    bool shutdown_pending_ = false, shutdown_ = false;
    bool moving_ = false;
    bool available_ = false;
    bool faulted_ = false;
    bool camera_faulted_ = false;
    bool foreground_ = false;
    bool keyboard_armed_ = false;
    bool controller_armed_ = false;
    bool drag_armed_ = false;
    bool controller_connected_ = false;
    bool drag_pending_ = false;
    bool drag_active_ = false;
    bool previous_drag_down_ = false;
    float drag_origin_x_ = 0;
    float drag_origin_y_ = 0;
    std::uint64_t last_tick_ = 0;
    bool has_tick_ = false;
};
} // namespace wonderbane::extension::movement
