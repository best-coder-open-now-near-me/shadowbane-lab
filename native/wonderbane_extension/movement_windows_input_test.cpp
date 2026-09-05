#include "movement_windows_input.h"
#include <CommCtrl.h>
#include <windowsx.h>
#include <atomic>
#include <iostream>
#include <string>
#include <thread>
#include <vector>
using namespace wonderbane::extension::movement;
namespace {
int failures = 0;
void Check(bool ok, const char* message) { if (!ok) { ++failures; std::cerr << message << '\n'; } }
HWND foreground = nullptr, client = nullptr;
std::array<SHORT, 256> keys{};
POINT pointer{10, 10};
bool ui_owned = false, pointer_owned = false, camera = false, connected = true;
DWORD selected_slot = 99; XINPUT_GAMEPAD pad{};
int original_keys = 0, stops = 0, safety = 0, terminal_safety = 0, native_down = 0, native_up = 0;
WPARAM native_move = 0;
std::uint32_t last_key = 0, last_mods = 0, last_down = 0, last_repeat = 0;
HWND WINAPI Focus() { return foreground; }
SHORT WINAPI KeyState(int key) { return keys[static_cast<std::size_t>(key)]; }
BOOL WINAPI Cursor(LPPOINT out) { *out = pointer; return ClientToScreen(client, out); }
DWORD WINAPI Controller(DWORD slot, XINPUT_STATE* out) noexcept {
    selected_slot = slot; out->Gamepad = pad; return connected ? ERROR_SUCCESS : ERROR_DEVICE_NOT_CONNECTED;
}
DWORD WINAPI Capabilities(DWORD slot, DWORD, XINPUT_CAPABILITIES* out) noexcept {
    selected_slot = slot; out->Type = XINPUT_DEVTYPE_GAMEPAD; out->SubType = XINPUT_DEVSUBTYPE_GAMEPAD;
    return connected ? ERROR_SUCCESS : ERROR_DEVICE_NOT_CONNECTED;
}
void __cdecl Original(std::uint32_t key, std::uint32_t mods, std::uint32_t down, std::uint32_t repeat) {
    ++original_keys; last_key = key; last_mods = mods; last_down = down; last_repeat = repeat;
}
void __cdecl Foreign(std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t) {}
bool Ui(void*, POINT, NativeUiState& out) noexcept {
    out.available = true; out.keyboard_owned = ui_owned; out.pointer_owned = pointer_owned;
    out.camera_gesture = camera; return true;
}
void Safety(void*, HWND hwnd, StopReason, bool terminal) noexcept {
    Check(hwnd == client, "safety binds exact HWND"); ++safety; if (terminal) { ++terminal_safety; }
}
LRESULT CALLBACK OriginalWindow(HWND hwnd, UINT message, WPARAM wp, LPARAM lp) {
    if (message == WM_XBUTTONDOWN || message == WM_RBUTTONDOWN) { ++native_down; return TRUE; }
    if (message == WM_XBUTTONUP || message == WM_RBUTTONUP) { ++native_up; return TRUE; }
    if (message == WM_MOUSEMOVE) { native_move = wp; }
    return DefWindowProcW(hwnd, message, wp, lp);
}
struct Actuator : NativeActuator {
    bool Stop(const Grant&, StopReason) noexcept override { ++stops; return true; }
    bool Direction(const Grant&, Vector2, bool) noexcept override { return true; }
    bool Destination(const Grant&, GroundPoint, bool) noexcept override { return true; }
    bool Camera(Vector2) noexcept override { return true; }
    void Revoked(const Grant&, const Grant&, StopReason) noexcept override {}
    void SceneRetired(std::uint64_t) noexcept override {}
};
}
namespace wonderbane::extension::movement {
bool VerifyNativeMovementImage(std::uintptr_t&) noexcept { return false; }
struct WindowsInputTestAccess {
    static bool Bind(WindowsInput& input, HWND hwnd, std::uint32_t* slot) {
        input.platform_ = {&Focus, &KeyState, &Cursor, &Controller, &Capabilities};
        return input.BindVerified(hwnd, slot, &Original);
    }
    static void ReplaceSubclass(HWND hwnd, DWORD_PTR owner) {
        Check(SetWindowSubclass(hwnd, &WindowsInput::Window, 0x57424d56, owner) != FALSE, "foreign subclass replacement installed");
    }
    static bool HasSubclass(HWND hwnd, DWORD_PTR owner) {
        DWORD_PTR actual = 0;
        return GetWindowSubclass(hwnd, &WindowsInput::Window, 0x57424d56, &actual) && actual == owner;
    }
    static void Key(std::uint32_t key, std::uint32_t mods, bool down, bool repeat = false) {
        WindowsInput::Keyboard(key, mods, down, repeat);
    }
};
}
int main(int argc, char** argv) {
    const std::string mode = argc > 1 ? argv[1] : "keyboard";
    WNDCLASSW klass{}; klass.lpfnWndProc = &OriginalWindow; klass.hInstance = GetModuleHandleW(nullptr);
    klass.lpszClassName = L"movement input test"; Check(RegisterClassW(&klass) != 0, "window class registered");
    client = CreateWindowW(klass.lpszClassName, L"input", WS_OVERLAPPEDWINDOW, 0, 0, 640, 480,
        nullptr, nullptr, klass.hInstance, nullptr); Check(client != nullptr, "native test HWND created");
    foreground = client;
    Actuator actuator; Controls controls(actuator); Settings settings; settings.enabled = settings.controller = true;
    settings.controller_slot = 2; Check(controls.Configure(settings) == Result::accepted, "configure controls");
    Input input{}; input.scene = 1; input.native_available = input.exact_foreground = true;
    input.tick_ms = 1; controls.Tick(input);
    WindowsInput windows(controls, {nullptr, &Ui, &Safety});
    std::uint32_t slot = reinterpret_cast<std::uint32_t>(&Original);
    if (mode == "rollback") {
        slot = reinterpret_cast<std::uint32_t>(&Foreign);
        Check(!WindowsInputTestAccess::Bind(windows, client, &slot) && !windows.Available(), "foreign native slot rejects registration");
        Check(slot == reinterpret_cast<std::uint32_t>(&Foreign), "failed registration preserves foreign native slot");
        Check(!WindowsInputTestAccess::HasSubclass(client, reinterpret_cast<DWORD_PTR>(&windows)), "failed registration removes only own window subclass");
        WindowsInputTestAccess::Key('W', 0, true);
        Check(original_keys == 1, "failed registration retains dispatched original call-through");
        DestroyWindow(client); return failures ? 1 : 0;
    }
    Check(WindowsInputTestAccess::Bind(windows, client, &slot) && windows.Available(), "real window and callback hooks installed");
    Check(windows.Configure(settings), "configure capture");
    const auto key = &WindowsInputTestAccess::Key;
    if (mode == "keyboard") {
        key('W', 0x14, true, false); key('W', 0x14, true, true);
        Check(original_keys == 0, "mapped native down and repeat suppressed");
        ui_owned = true; key('W', 0, false, false);
        Check(original_keys == 0, "UI entry still consumes paired release");
        key('W', 4, true, false); Check(original_keys == 1 && last_mods == 4, "text entry preserves original key ABI");
        ui_owned = false; key('W', 0, true, true); key('W', 0, false, false);
        Check(original_keys == 3 && last_key == 'W' && last_down == 0 && last_repeat == 0,
              "original-owned down retains original repeat and release after UI exit");
        key('W', 0, true, false); settings.enabled = false; Check(windows.Configure(settings), "disable capture");
        key('W', 0, false, false); Check(original_keys == 3, "disable preserves outstanding suppressed pair");
        controls.Configure(settings); key('W', 0, true, false); key('W', 0, false, false);
        Check(original_keys == 5, "disabled new input retains native behavior");
        foreground = nullptr; key('A', 7, true, false); Check(original_keys == 6, "other foreground keeps native action");
        std::thread other([&] { key('D', 9, true, false); }); other.join();
        Check(original_keys == 7 && last_mods == 9, "foreign thread only forwards original callback");
    } else if (mode == "mouse") {
        const auto down = MAKEWPARAM(MK_XBUTTON1, XBUTTON1), up = MAKEWPARAM(0, XBUTTON1);
        SendMessageW(client, WM_XBUTTONDOWN, down, MAKELPARAM(10, 10));
        Check(native_down == 0 && GetCapture() == client, "eligible down buffered with real capture");
        SendMessageW(client, WM_MOUSEMOVE, MK_XBUTTON1, MAKELPARAM(13, 10));
        Check(!(native_move & MK_XBUTTON1), "original hover never sees unmatched held button");
        SendMessageW(client, WM_XBUTTONUP, up, MAKELPARAM(13, 10));
        Check(native_down == 1 && native_up == 1 && GetCapture() != client, "ordinary click delivers its original pair once");
        SendMessageW(client, WM_XBUTTONDOWN, down, MAKELPARAM(10, 10));
        pointer = {30, 10}; SendMessageW(client, WM_MOUSEMOVE, MK_XBUTTON1, MAKELPARAM(30, 10));
        CapturedInput snapshot{}; Check(windows.Snapshot(snapshot) && snapshot.press_origin
            && snapshot.press_origin->x == 10 && snapshot.input.pointer_x == 30 && snapshot.input.keys[5],
            "first delayed update retains actual press origin and current pointer");
        SendMessageW(client, WM_XBUTTONUP, up, MAKELPARAM(30, 10));
        Check(native_down == 1 && native_up == 1 && windows.Snapshot(snapshot) && !snapshot.input.keys[5],
              "drag release consumed and reflected without original click");
        pointer_owned = true;
        SendMessageW(client, WM_XBUTTONDOWN, down, MAKELPARAM(10, 10));
        SendMessageW(client, WM_XBUTTONUP, up, MAKELPARAM(10, 10));
        Check(native_down == 2 && native_up == 2, "inventory and map UI keep original pair");
        pointer_owned = false;
        SendMessageW(client, WM_RBUTTONDOWN, MK_RBUTTON, MAKELPARAM(10, 10));
        SendMessageW(client, WM_RBUTTONUP, 0, MAKELPARAM(10, 10));
        Check(native_down == 3 && native_up == 3, "native right camera gesture retained");
        SendMessageW(client, WM_XBUTTONDOWN, down, MAKELPARAM(10, 10));
        SendMessageW(client, WM_MOUSEMOVE, MK_XBUTTON1, MAKELPARAM(40, 10));
        const auto before = safety; ReleaseCapture();
        Check(safety == before + 1 && windows.Snapshot(snapshot) && !snapshot.input.keys[5],
              "lost actual capture synchronously notifies safety without native update");
        // Missing release outside capture must not swallow a fresh original pair.
        pointer_owned = true;
        SendMessageW(client, WM_XBUTTONDOWN, down, MAKELPARAM(10, 10));
        SendMessageW(client, WM_XBUTTONUP, up, MAKELPARAM(10, 10));
        Check(native_down == 4 && native_up == 4, "fresh pair survives an abandoned capture");
    } else if (mode == "controller") {
        CapturedInput out{}; Check(windows.Snapshot(out) && !out.input.controller_connected, "initial controller neutral rearm edge");
        pad.sThumbLX = -32768; pad.sThumbLY = 16384; pad.sThumbRX = 32767;
        Check(windows.Snapshot(out) && selected_slot == 2 && out.input.controller_connected
            && out.input.left_stick.x == -1 && out.input.left_stick.y > 0.5F && out.input.right_stick.x == 1,
            "explicit slot preserves full analog direction and signed endpoints");
        const auto before = safety; SendMessageW(client, WM_DEVICECHANGE, 0, 0);
        Check(safety == before, "device change without manual owner cannot cancel a route");
        Check(windows.Snapshot(out) && !out.input.controller_connected, "device event forces disconnect edge");
        connected = false; Check(windows.Snapshot(out) && !out.input.controller_connected
            && out.input.left_stick.x == 0, "disconnect cannot retain stale axes");
        connected = true; foreground = nullptr;
        Check(windows.Snapshot(out) && !out.input.controller_connected && !out.input.exact_foreground,
              "same controller cannot move background client");
        foreground = client; camera = true;
        Check(windows.Snapshot(out) && out.input.camera_blocked && out.input.right_stick.x == 1,
              "native camera gesture gates camera without falsifying stick neutral");
    } else if (mode == "foreign-subclass") {
        WindowsInputTestAccess::ReplaceSubclass(client, 0);
        Check(!windows.Available(), "foreign subclass ownership disables capture");
        windows.Retire();
        Check(WindowsInputTestAccess::HasSubclass(client, 0), "retirement leaves foreign subclass ownership intact");
    } else if (mode == "lifecycle") {
        SendMessageW(client, WM_KILLFOCUS, 0, 0); Check(safety == 1, "focus loss notifies with no native update");
        slot = reinterpret_cast<std::uint32_t>(&Foreign);
        Check(!windows.Available(), "foreign slot disables input immediately");
        windows.Retire(); Check(slot == reinterpret_cast<std::uint32_t>(&Foreign), "retirement preserves foreign keyboard hook");
        key('W', 4, true, false); Check(original_keys == 1, "already fetched callback retains original after retirement");
    } else { Check(false, "unknown mode"); }
    DestroyWindow(client);
    if (mode != "lifecycle" && mode != "foreign-subclass") { Check(terminal_safety == 1, "destruction retires authority synchronously"); }
    Check(!windows.Available(), "destroyed HWND never remains usable");
    return failures ? 1 : 0;
}
