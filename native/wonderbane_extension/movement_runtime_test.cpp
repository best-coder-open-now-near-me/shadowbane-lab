// Reuse the native backend's real call composition fixture. Native functions
// are controlled test callees; Runtime, Controls, HWND capture and cancellation
// execute production implementations, without opening a game process.
#define main NativeBackendRegressionMain
#include "movement_native_stop_test.cpp"
#undef main
#include "movement_runtime.cpp"
#include <string>
namespace wm = wonderbane::extension::movement;
namespace {
wm::NativeScene observed{};
bool alive = true, ui_blocked = false, device_connected = true;
HWND focused = nullptr, bound_window = nullptr;
std::array<SHORT, 256> physical_keys{};
POINT pointer{0, 0}; XINPUT_GAMEPAD gamepad{};
std::uint64_t clock_tick = 0;
char interrupt_phase = 0;
int retired_updates = 0;
HWND WINAPI Focus() { return focused; }
SHORT WINAPI PhysicalKey(int key) { return physical_keys[static_cast<std::size_t>(key)]; }
BOOL WINAPI Cursor(LPPOINT out) { *out = pointer; return ClientToScreen(bound_window, out); }
ULONGLONG WINAPI Clock() { clock_tick += 16; return clock_tick; }
DWORD WINAPI Controller(DWORD, XINPUT_STATE* out) noexcept {
    out->Gamepad = gamepad; return device_connected ? ERROR_SUCCESS : ERROR_DEVICE_NOT_CONNECTED;
}
DWORD WINAPI Capabilities(DWORD, DWORD, XINPUT_CAPABILITIES* out) noexcept {
    out->Type = XINPUT_DEVTYPE_GAMEPAD; out->SubType = XINPUT_DEVSUBTYPE_GAMEPAD;
    return device_connected ? ERROR_SUCCESS : ERROR_DEVICE_NOT_CONNECTED;
}
void __cdecl OriginalKey(std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t) {}
bool Ui(void*, POINT, wm::NativeUiState& out) noexcept {
    out.available = true; out.keyboard_owned = ui_blocked; out.pointer_owned = ui_blocked; return true;
}
void Interrupt(char phase) {
    if (phase == interrupt_phase) {
        interrupt_phase = 0;
        SendMessageW(bound_window, WM_KILLFOCUS, 0, 0);
    }
}
}
namespace wonderbane::extension {
DWORD StartNativeMovementUpdates(const ProcessIdentity&, NativeMovementUpdate) noexcept { return ERROR_SUCCESS; }
void StopNativeMovementUpdates() noexcept { ++retired_updates; }
namespace movement {
bool NativeMovementLifetimeCurrent(const NativeScene& scene) noexcept {
    return alive && scene.epoch && scene.epoch == observed.epoch && scene.actor == observed.actor
        && scene.world == observed.world && scene.window == observed.window && scene.parent == observed.parent;
}
bool ObserveNativeMovementLifetime(void* window, NativeScene& scene) noexcept {
    scene = observed; return alive && reinterpret_cast<std::uintptr_t>(window) == observed.window;
}
bool StartNativeMovementLifetime(HWND) noexcept { return true; }
void RetireNativeMovementLifetime() noexcept { alive = false; }
struct NativeUiTestAccess { static void Bind(NativeUi& ui) { ui.bound_ = true; } };
struct WindowsInputTestAccess {
    static bool Bind(WindowsInput& input, HWND window, std::uint32_t* slot) {
        input.platform_ = {&Focus, &PhysicalKey, &Cursor, &Controller, &Capabilities};
        input.callbacks_.ui = &Ui;
        return input.BindVerified(window, slot, &OriginalKey);
    }
};
}
}
int main(int argc, char** argv) {
    const std::string mode = argc > 1 ? argv[1] : "keyboard";
    Fixture f; auto& rt = wm::runtime;
    if (mode == "startup-unavailable") {
        rt.process = {GetCurrentProcessId(), 42}; rt.Update(f.game_window.data());
        wm::RuntimeSnapshot snapshot{};
        Check(rt.terminal && !rt.initialized && retired_updates == 1 && wm::ReadNativeMovementControls(snapshot)
            && snapshot.terminal && !snapshot.bindings_available,
            "unsupported startup retires consumer and publishes unavailable without a guessed HWND");
        return failures ? 1 : 0;
    }
    f.runtime_composition = f.basis_mode = true;
    f.on_native = &Interrupt; focused = bound_window = f.window;
    rt.window = f.window; rt.thread = GetCurrentThreadId(); rt.initialized = true; rt.clock = &Clock;
    rt.process = {GetCurrentProcessId(), 42}; rt.settings.enabled = rt.settings.controller = true;
    wm::NativeStopTestAccess::Bind(rt.native, f.base, f.window); rt.native.EndUpdate();
    wm::NativeUiTestAccess::Bind(rt.ui);
    observed = {reinterpret_cast<std::uintptr_t>(f.actor.data()), 0,
        reinterpret_cast<std::uintptr_t>(f.world.data()), reinterpret_cast<std::uintptr_t>(f.game_window.data()), {17, 31}, 1};
    std::uint32_t slot = reinterpret_cast<std::uint32_t>(&OriginalKey);
    Check(wm::WindowsInputTestAccess::Bind(rt.input, f.window, &slot), "consumer input hook installed");
    Check(rt.controls.Configure(rt.settings) == wm::Result::accepted && rt.input.Configure(rt.settings), "consumer settings configured");
    const auto step = [&] { rt.Update(f.game_window.data()); };
    step(); step();
    Token token{}; std::memcpy(token.worker.data(), "worker", 6); std::memcpy(token.operation.data(), "route", 5);
    Grant automation{};
    Check(rt.native.BeginUpdate(f.game_window.data(), observed), "automation admission uses native owner phase");
    Check(rt.controls.AcquireAutomation(rt.controls.Current().generation, token, automation) == Result::accepted, "existing route acquires ownership");
    GroundPoint route_point{}; f.real_pick_move = true;
    Check(rt.native.PickGround(0, 0, route_point)
        && rt.controls.AutomationDestination(automation, route_point) == Result::accepted,
        "automation owns an actual native movement before manual takeover");
    rt.native.EndUpdate(); f.real_pick_move = false; f.moves = 0;
    const auto drive = [&] {
        if (mode == "controller") { gamepad.sThumbLY = 32767; }
        else if (mode == "drag") {
            f.real_pick_move = true;
            SendMessageW(f.window, WM_XBUTTONDOWN, MAKEWPARAM(MK_XBUTTON1, XBUTTON1), MAKELPARAM(0, 0));
            pointer = {20, 0}; SendMessageW(f.window, WM_MOUSEMOVE, MK_XBUTTON1, MAKELPARAM(20, 0));
        } else { physical_keys['W'] = static_cast<SHORT>(0x8000); }
        step();
    };
    if (mode == "nested-stop") { interrupt_phase = 's'; f.Arm(false); drive(); }
    else if (mode == "nested-camera") { interrupt_phase = 'c'; gamepad.sThumbRX = 32767; drive(); }
    else if (mode == "nested-move") { interrupt_phase = 'd'; drive(); }
    else { drive(); }
    if (mode.starts_with("nested-")) {
        Check(rt.controls.Current().owner == Owner::none && f.moves == (mode == "nested-move" ? 1 : 0),
              "nested HWND safety cancels before any later movement dispatch");
        Check(Get<std::uint32_t>(f.state.data(), 0x10) == 5 && rt.pending_count == 0,
              "nested safety drains production stopped state before consumer returns");
        step(); Check(rt.controls.Current().owner == Owner::none, "nested safety disarms held controls");
    } else {
        Check(rt.controls.Current().owner == Owner::manual && f.moves >= 1, "manual input takes existing automation through native backend");
        const auto manual = rt.controls.Current(); const auto sends = f.sends;
        Check(rt.controls.AutomationDestination(automation, {}) == Result::stale
            && rt.controls.Stop(automation) == Result::stale && f.sends == sends,
            "delayed automation move and stop cannot affect accepted manual owner");
        if (mode == "settings-stale") {
            wm::RuntimeSnapshot expected{}; rt.Publish(); wm::ReadNativeMovementControls(expected);
            expected.grant = automation;
            Check(rt.Configure(expected, rt.settings) == Result::stale && rt.controls.Current() == manual
                && f.sends == sends, "old settings ticket cannot cancel a new movement owner");
        } else if (mode == "scene-stale") {
            alive = false; rt.ApplySafety({f.window, observed, manual, StopReason::focus});
            Check(rt.controls.Current().scene == 0 && f.sends == sends,
                  "unverified retired lifetime discards authority without recapturing actor");
        } else if (mode == "chat") {
            ui_blocked = true; step();
            Check(rt.controls.Current().owner == Owner::none && Get<std::uint32_t>(f.state.data(), 0x10) == 5,
                  "chat entry stops native movement");
            ui_blocked = false; const auto moves = f.moves; step();
            Check(f.moves == moves, "held keys cannot resume on chat exit");
        } else if (mode == "focus") {
            SendMessageW(f.window, WM_KILLFOCUS, 0, 0);
            Check(rt.controls.Current().owner == Owner::none && f.sends == sends + 1
                && Get<std::uint32_t>(f.state.data(), 0x10) == 5,
                "actual HWND focus event executes native stop without a later update");
        } else if (mode == "stale") {
            rt.ApplySafety({f.window, observed, automation, StopReason::focus});
            Check(rt.controls.Current() == manual && f.sends == sends, "obsolete queued window stop cannot revoke new owner");
        } else if (mode == "destroyed") {
            const auto calls = f.state_calls; DestroyWindow(f.window); f.window = nullptr;
            Check(rt.terminal && rt.controls.Current().scene == 0 && f.state_calls == calls && retired_updates == 1,
                  "window destruction retires authority without native mutation after invalidation");
        } else {
            physical_keys.fill(0); gamepad = {};
            if (mode == "drag") { SendMessageW(f.window, WM_XBUTTONUP, MAKEWPARAM(0, XBUTTON1), MAKELPARAM(20, 0)); }
            step();
            Check(Get<std::uint32_t>(f.state.data(), 0x10) == 5 && f.sends == sends + 1,
                  "manual release follows actual native stop path");
            const auto moves = f.moves; step(); Check(f.moves == moves, "release never resumes route");
        }
    }
    if (!rt.terminal) { rt.input.Retire(); }
    return failures ? 1 : 0;
}
