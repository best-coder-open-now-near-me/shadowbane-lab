#include "movement_runtime.h"
#include "movement_boundary_trace.h"
#include "movement_native_stop.h"
#include "movement_native_ui.h"
#include "movement_windows_input.h"
#include "movement_lifetime.h"
#include <array>
#include <atomic>
#include <optional>
namespace wonderbane::extension::movement {
namespace {
class Runtime final : public NativeActuator {
public:
    Controls controls{*this};
    NativeStop native{controls};
    NativeUi ui;
    WindowsInput input{controls, {this, &QueryUi, &SafetyEvent}};
    ProcessIdentity process{};
    Settings settings{};
    NativeScene scene{};
    HWND window = nullptr;
    DWORD thread = 0;
    std::uint64_t revision = 1, tick = 0;
    decltype(&GetTickCount64) clock = &GetTickCount64;
    bool initialized = false, initializing = false, busy = false, destroyed = false, terminal = false;
    bool lifetime_started = false;
    std::optional<StopReason> interrupted;
    struct SafetyCommand { HWND window; NativeScene scene; Grant grant; StopReason reason; };
    std::array<SafetyCommand, 8> pending{};
    std::size_t pending_count = 0;
    SRWLOCK publication_lock = SRWLOCK_INIT;
    RuntimeSnapshot published{};
    std::atomic<bool> started{false};
    static bool QueryUi(void* context, POINT point, NativeUiState& result) noexcept {
        auto& self = *static_cast<Runtime*>(context);
        return !self.destroyed && !self.terminal && self.native.Available()
            && NativeMovementLifetimeCurrent(self.scene) && self.ui.Snapshot(point, result);
    }
    static void SafetyEvent(void* context, HWND source, StopReason reason, bool destroying) noexcept {
        static_cast<Runtime*>(context)->Safety(source, reason, destroying);
    }
    bool Stop(const Grant& grant, StopReason) noexcept override {
        return !destroyed && !terminal && native.Execute(grant);
    }
    bool Direction(const Grant& grant, Vector2 direction, bool start) noexcept override {
        return !destroyed && !terminal && !interrupted && native.Steer(grant, direction, tick, start);
    }
    bool Destination(const Grant& grant, GroundPoint point, bool) noexcept override {
        return !destroyed && !terminal && !interrupted && native.MoveToPick(grant, point);
    }
    bool Camera(Vector2 radians) noexcept override {
        return !destroyed && !terminal && !interrupted && native.RotateCamera(radians);
    }
    void Revoked(const Grant&, const Grant&, StopReason) noexcept override {}
    void SceneRetired(std::uint64_t epoch) noexcept override { native.SceneRetired(epoch); }
    std::optional<StopReason> Interrupted() const noexcept override { return interrupted; }
    void Publish() noexcept {
        RuntimeSnapshot next{}; next.process = process; next.window = window; next.settings = settings;
        next.grant = controls.Current(); next.settings_revision = revision; next.terminal = terminal || destroyed;
        next.bindings_available = !next.terminal && initialized && native.Available() && ui.Available()
            && input.Available() && NativeMovementLifetimeCurrent(scene);
        next.ready = next.bindings_available && controls.Ready();
        next.camera_available = next.bindings_available && controls.CameraReady();
        AcquireSRWLockExclusive(&publication_lock); published = next; ReleaseSRWLockExclusive(&publication_lock);
    }
    void FinishDestroyed() noexcept {
        if (busy || GetCurrentThreadId() != thread) { return; }
        destroyed = terminal = true;
        // HWND destruction is loss of authority, never permission to recapture
        // or stop a replacement actor. Native callbacks already in flight retain
        // their original and finish their own exact-lifetime cleanup.
        controls.ObserveScene(0); controls.Shutdown(); pending_count = 0; scene = {};
        input.Retire();
        if (lifetime_started) { RetireNativeMovementLifetime(); }
        StopNativeMovementUpdates(); Publish();
    }
    void Queue(const SafetyCommand& command) noexcept {
        for (std::size_t i = 0; i < pending_count; ++i) {
            if (pending[i].window == command.window && pending[i].grant == command.grant
                && pending[i].scene.epoch == command.scene.epoch) { return; }
        }
        if (pending_count < pending.size()) { pending[pending_count++] = command; }
        // Overflow remains an input interruption; no normal writer is admitted
        // until the owning-thread drain and neutral rearm have completed.
    }
    void ApplySafety(const SafetyCommand& command) noexcept {
        if (terminal || destroyed || command.window != window || command.grant != controls.Current()
            || command.scene.epoch != scene.epoch || GetCurrentThreadId() != thread) { return; }
        if (!NativeMovementLifetimeCurrent(command.scene)) {
            controls.ObserveScene(0); scene = {}; return;
        }
        busy = true;
        if (native.BeginOwnerStop(command.window, reinterpret_cast<void*>(command.scene.window), command.scene)) {
            (void)controls.EmergencyStop(command.grant, command.reason);
            native.EndUpdate();
        } else {
            // This records failed cancellation and excludes another writer. The
            // adapter cannot mutate without its admitted stop-only phase.
            (void)controls.EmergencyStop(command.grant, StopReason::binding_failure);
        }
        busy = false;
    }
    void Drain() noexcept {
        if (busy || GetCurrentThreadId() != thread) { return; }
        if (destroyed) { FinishDestroyed(); return; }
        // Only a bounded number of immutable commands per dispatch; a nested
        // repeated notification for a retired generation becomes a no-op.
        for (std::size_t budget = 0; pending_count && budget < pending.size(); ++budget) {
            const auto command = pending[0];
            for (std::size_t i = 1; i < pending_count; ++i) { pending[i - 1] = pending[i]; }
            --pending_count; ApplySafety(command);
            if (destroyed) { FinishDestroyed(); return; }
        }
        if (!pending_count) { interrupted.reset(); }
        Publish();
    }
    void Safety(HWND source, StopReason reason, bool destroying) noexcept {
        if (source != window || GetCurrentThreadId() != thread || terminal) { return; }
        if (destroying) { destroyed = true; interrupted = StopReason::shutdown; Drain(); return; }
        // Device notifications and pointer-capture loss cannot revoke automation
        // merely because the user is looking around during a route.
        if ((reason == StopReason::device_lost || reason == StopReason::capture_lost)
            && controls.Current().owner != Owner::manual) { return; }
        interrupted = reason;
        Queue({source, scene, controls.Current(), reason}); Drain();
    }
    bool Initialize() noexcept {
        if (initializing || terminal || destroyed) { return false; }
        initializing = true; thread = GetCurrentThreadId();
        bool success = NativeInputWindow(window);
        DWORD pid = 0; const auto window_thread = GetWindowThreadProcessId(window, &pid);
        success = success && window_thread == thread && pid == process.process_id;
        if (success) { success = native.Bind(window) && ui.Bind(window); }
        if (success) { lifetime_started = StartNativeMovementLifetime(window); success = lifetime_started; }
        if (success) { success = input.Bind(window); }
        if (success) { success = controls.Configure(settings) == Result::accepted && input.Configure(settings); }
        initialized = success; initializing = false;
        if (!success) { destroyed = true; FinishDestroyed(); }
        return success;
    }
    void Update(void* receiver) noexcept {
        if (busy || initializing || terminal || destroyed) { return; }
        if (!initialized && !Initialize()) { return; }
        if (GetCurrentThreadId() != thread) { return; }
        Drain(); if (terminal || destroyed || pending_count) { return; }
        busy = true; interrupted.reset(); tick = clock();
        NativeScene next{};
        const bool observed = ObserveNativeMovementLifetime(receiver, next);
        scene = observed ? next : NativeScene{};
        controls.ObserveScene(scene.epoch);
        CapturedInput captured{};
        const bool captured_ok = input.Snapshot(captured);
        auto& sampled = captured.input; sampled.tick_ms = tick; sampled.scene = scene.epoch;
        const bool phase = observed && native.BeginUpdate(receiver, scene);
        sampled.native_available = phase && captured_ok && native.Available();
        if (phase && captured_ok && sampled.exact_foreground && !sampled.ui_owns_input && settings.enabled) {
            sampled.camera_basis_valid = native.CameraBasis(sampled.camera_forward, sampled.camera_right);
            if (captured.press_origin) {
                GroundPoint press_point{};
                const auto press = *captured.press_origin;
                sampled.press_origin = DragPress{static_cast<float>(press.x), static_cast<float>(press.y),
                    native.PickGround(press.x, press.y, press_point)};
            }
            // Basis and press queries clear native pick scratch. The final pick
            // retained for Destination is always the current pointer's terrain hit.
            if (sampled.pointer_in_world && sampled.capture_valid) {
                sampled.ground_valid = native.PickGround(static_cast<int>(sampled.pointer_x),
                    static_cast<int>(sampled.pointer_y), sampled.ground);
            }
        }
        controls.Tick(sampled);
        if (phase) { native.EndUpdate(); }
        busy = false; Drain(); Publish();
    }
    Result Configure(const RuntimeSnapshot& expected, const Settings& next) noexcept {
        if (busy || terminal || destroyed || GetCurrentThreadId() != thread) { return Result::inhibited; }
        if (expected.process.process_id != process.process_id
            || expected.process.creation_filetime_utc != process.creation_filetime_utc
            || expected.window != window || expected.grant != controls.Current()
            || expected.settings_revision != revision) { return Result::stale; }
        if (!ValidSettings(next) || revision == UINT64_MAX) { return Result::invalid; }
        if (!NativeMovementLifetimeCurrent(scene)
            || !native.BeginOwnerStop(window, reinterpret_cast<void*>(scene.window), scene)) { return Result::unavailable; }
        busy = true; interrupted.reset();
        auto result = controls.Configure(next);
        if (result == Result::accepted || result == Result::stop_failed) {
            if (input.Configure(next)) { settings = next; ++revision; }
            else { controls.Shutdown(); result = Result::unavailable; }
        }
        native.EndUpdate(); busy = false; Drain(); Publish(); return result;
    }
};
Runtime runtime;
void Update(void* receiver, double) noexcept { runtime.Update(receiver); }
}
DWORD StartNativeMovementControls(const ProcessIdentity& process) noexcept {
    if (!process.process_id || process.process_id != GetCurrentProcessId() || !process.creation_filetime_utc) { return ERROR_INVALID_PARAMETER; }
    bool expected = false;
    if (!runtime.started.compare_exchange_strong(expected, true)) { return ERROR_ALREADY_INITIALIZED; }
    runtime.process = process;
    const auto result = StartNativeMovementUpdates(process, &Update);
    if (result != ERROR_SUCCESS) {
        runtime.terminal = true;
        AcquireSRWLockExclusive(&runtime.publication_lock);
        runtime.published.process = process; runtime.published.terminal = true;
        ReleaseSRWLockExclusive(&runtime.publication_lock);
    }
    return result;
}
bool ReadNativeMovementControls(RuntimeSnapshot& out) noexcept {
    AcquireSRWLockShared(&runtime.publication_lock); out = runtime.published;
    ReleaseSRWLockShared(&runtime.publication_lock); return out.process.process_id != 0;
}
Result ConfigureNativeMovementControls(const RuntimeSnapshot& expected, const Settings& settings) noexcept {
    return runtime.Configure(expected, settings);
}
}
