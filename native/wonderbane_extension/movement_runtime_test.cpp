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
    if (mode == "ipc") {
        FILETIME created{}, exited{}, kernel{}, user{};
        Check(GetProcessTimes(GetCurrentProcess(), &created, &exited, &kernel, &user) != FALSE, "IPC client lifetime");
        rt.process = {GetCurrentProcessId(), (static_cast<std::uint64_t>(created.dwHighDateTime) << 32) | created.dwLowDateTime};
        rt.clock = &GetTickCount64;
        rt.settings.enabled = false;
        Check(rt.controls.Configure(rt.settings) == wm::Result::accepted && rt.input.Configure(rt.settings),
            "manual disabled retains native automation readiness");
        Check(wonderbane::extension::StartClientActionCommandChannel(rt.process) == ERROR_SUCCESS, "IPC production channel");
        step(); step(); rt.Publish();
        std::printf("%lu %llu %llu\n", static_cast<unsigned long>(rt.process.process_id),
            static_cast<unsigned long long>(rt.process.creation_filetime_utc),
            static_cast<unsigned long long>(reinterpret_cast<std::uintptr_t>(f.window))); std::fflush(stdout);
        const auto until = GetTickCount64() + 10000;
        auto* storage = wonderbane::extension::command_channel_detail::g_runtime.storage;
        while (GetTickCount64() < until && InterlockedCompareExchange64(&storage->header.result_read_sequence, 0, 0) < 6) {
            step(); Sleep(5);
        }
        Check(storage->header.result_read_sequence == 6, "Python consumed six correlated native receipts");
        wonderbane::extension::StopClientActionCommandChannel(); rt.input.Retire(); return failures ? 1 : 0;
    }
    if (mode == "commands") {
        auto lease = std::make_shared<wm::CommandLease>();
        lease->process = OpenProcess(SYNCHRONIZE, FALSE, GetCurrentProcessId());
        lease->host = {GetCurrentProcessId(), 9, 42};
        bool lease_current = true; lease->context = &lease_current;
        lease->validate = [](void* context, const wm::wire::Host&, std::uint64_t) noexcept { return *static_cast<bool*>(context); };
        const auto make = [&](wm::wire::Verb verb, wm::Grant expected, unsigned char key) {
            auto command = std::make_shared<wm::QueuedCommand>(); command->id = key; command->sequence = key;
            command->deadline = 100000; command->verb = verb; command->lease = lease;
            command->command.host = lease->host; command->command.window = reinterpret_cast<std::uintptr_t>(f.window);
            command->command.expected = wm::wire::Encode(expected); command->command.request[0] = key;
            command->command.settings = wm::wire::Encode(rt.settings); command->command.revision = rt.revision;
            if (verb == wm::wire::Verb::acquire) {
                std::memcpy(command->command.requested.worker, "worker", 6);
                std::memcpy(command->command.requested.operation, "route", 5);
            }
            return command;
        };
        const auto run = [&](const std::shared_ptr<wm::QueuedCommand>& command) {
            Check(wm::QueueMovementCommand(command), "command admitted once"); step();
            Check(command->state.load() == 2, "owning update publishes receipt"); wm::ReleaseMovementCommand(command);
        };
        const auto original = rt.controls.Current(); auto acquire = make(wm::wire::Verb::acquire, original, 1);
        run(acquire); const auto owned = rt.controls.Current();
        Check(acquire->receipt.outcome == 0 && owned.owner == wm::Owner::automation, "queued acquire obtains native owner");
        auto retry = make(wm::wire::Verb::acquire, original, 1); run(retry);
        Check(retry->receipt.outcome == 0 && rt.controls.Current() == owned
            && std::memcmp(&retry->receipt, &acquire->receipt, sizeof(retry->receipt)) == 0,
            "ambiguous retry returns original immutable receipt without reacquisition");
        auto moving = make(wm::wire::Verb::destination, owned, 5); moving->command.destination = {30, 0, -40}; run(moving);
        Check(moving->receipt.outcome == 0 && f.destination.x == 130 && f.destination.z == -240,
            "queued world move uses terrain hit transformed by native parent helper");
        auto pause = make(wm::wire::Verb::pause, owned, 6); run(pause);
        Check(pause->receipt.outcome == 0 && rt.controls.Current() == owned && Get<std::uint32_t>(f.state.data(), 0x10) == 5,
            "pause cancels native movement while retaining operation grant");
        auto resumed = make(wm::wire::Verb::destination, owned, 7); resumed->command.destination = {31, 0, -41}; run(resumed);
        Check(resumed->receipt.outcome == 0 && rt.controls.Current() == owned, "next PvE approach uses same immutable grant");
        auto delayed = make(wm::wire::Verb::stop, owned, 2);
        physical_keys['W'] = static_cast<SHORT>(0x8000); run(delayed);
        const auto manual = rt.controls.Current();
        Check(delayed->receipt.outcome == static_cast<unsigned>(wm::Result::stale)
            && manual.owner == wm::Owner::manual, "manual Tick precedes delayed automation stop");
        lease_current = false; step(); Check(rt.controls.Current() == manual, "obsolete lease loss cannot stop manual owner");
        physical_keys.fill(0); step(); lease_current = true;
        auto expired = make(wm::wire::Verb::acquire, rt.controls.Current(), 3); expired->deadline = 1; run(expired);
        Check(expired->receipt.outcome == static_cast<unsigned>(wm::Result::stale), "expired command never reacquires");
        auto replacement = make(wm::wire::Verb::acquire, rt.controls.Current(), 4); run(replacement);
        Check(replacement->receipt.outcome == 0, "explicit new request resumes automation");
        lease_current = false; step(); Check(rt.controls.Current().owner == wm::Owner::none, "current lease loss cancels its exact owner");
        lease_current = true;
        std::shared_ptr<wm::QueuedCommand> latest;
        for (unsigned n = 0; n < 150; ++n) {
            auto next = make(wm::wire::Verb::acquire, rt.controls.Current(), static_cast<unsigned char>(n + 10));
            next->command.request[1] = 1; run(next); latest = next;
            Check(next->receipt.outcome == 0 && rt.acquisitions.size() <= rt.acquisition_capacity,
                "long operation sequence keeps bounded receipts");
        }
        auto latest_retry = make(wm::wire::Verb::acquire, {}, 200); latest_retry->command = latest->command; run(latest_retry);
        Check(latest_retry->receipt.outcome == 0 && std::memcmp(&latest_retry->receipt, &latest->receipt, sizeof(latest->receipt)) == 0,
            "latest ambiguous acquisition survives journal retirement");
        auto old_retry = make(wm::wire::Verb::acquire, original, 1); run(old_retry);
        Check(old_retry->receipt.outcome == static_cast<unsigned>(wm::Result::stale), "evicted acquisition cannot mint authority");
        rt.input.Retire(); return failures ? 1 : 0;
    }
    Token token{}; std::memcpy(token.worker.data(), "worker", 6); std::memcpy(token.operation.data(), "route", 5);
    Grant automation{};
    Check(rt.native.BeginUpdate(f.game_window.data(), observed), "automation admission uses native owner phase");
    Check(rt.controls.AcquireAutomation(rt.controls.Current().generation, token, automation) == Result::accepted, "existing route acquires ownership");
    GroundPoint route_point{}; f.real_pick_move = true;
    Check(rt.native.PickGround(0, 0, route_point)
        && rt.controls.AutomationDestination(automation, {30, 0, -40}) == Result::accepted,
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
