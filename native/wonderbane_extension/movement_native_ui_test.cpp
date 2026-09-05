#include "movement_native_ui.h"
#include <array>
#include <atomic>
#include <cstring>
#include <iostream>
#include <thread>
namespace wm = wonderbane::extension::movement;
namespace {
int failures = 0, hits = 0;
void Check(bool ok, const char* label) { if (!ok) { ++failures; std::cerr << label << '\n'; } }
std::uintptr_t image = 0, native_window = 0;
wm::NativeUi* active_ui = nullptr;
bool text = false, hit = false, change_scene = false, reenter = false, raise_fault = false;
void* focused = nullptr;
POINT last_hit{};
template<class T> void Put(std::uintptr_t address, const T& value) { std::memcpy(reinterpret_cast<void*>(address), &value, sizeof(value)); }
bool __cdecl Text() { return text; }
void* __fastcall Focused(void* receiver, void*) { Check(receiver == reinterpret_cast<void*>(native_window), "native focused-control receiver"); return focused; }
void* __fastcall Hit(void* receiver, void*, int x, int y) {
    Check(receiver == reinterpret_cast<void*>(native_window), "native top-level hit receiver");
    ++hits; last_hit = {x, y};
    if (change_scene) { Put(image + 0x16a7bfc, std::uintptr_t{0}); }
    if (reenter) { wm::NativeUiState nested; Check(!active_ui->Snapshot({1, 1}, nested) && nested.keyboard_owned, "reentrant native query suppressed"); }
    if (raise_fault) { RaiseException(0xe0000042, 0, 0, nullptr); }
    return hit ? reinterpret_cast<void*>(0x12340000) : nullptr;
}
}
namespace wonderbane::extension::movement {
bool VerifyNativeMovementImage(std::uintptr_t&) noexcept { return false; }
struct NativeUiTestAccess {
    static void Bind(NativeUi& ui, HWND window) {
        ui.base_ = image; ui.window_ = window; ui.thread_ = GetCurrentThreadId(); ui.bound_ = true;
        ui.calls_.text = &Text;
        ui.calls_.focused = reinterpret_cast<decltype(ui.calls_.focused)>(&Focused);
        ui.calls_.hit = reinterpret_cast<decltype(ui.calls_.hit)>(&Hit);
    }
};
}
int main() {
    image = reinterpret_cast<std::uintptr_t>(VirtualAlloc(nullptr, 0x1766000, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE));
    std::array<std::uint8_t, 0x200> window_data{}, manager{};
    std::array<std::uint8_t, 0x400> control{};
    native_window = reinterpret_cast<std::uintptr_t>(window_data.data());
    const auto window = CreateWindowExW(0, L"STATIC", L"native-ui", 0, 0, 0, 640, 480, HWND_MESSAGE, nullptr, GetModuleHandleW(nullptr), nullptr);
    Check(image && window, "UI fixture allocation");
    RECT actual{}; Check(GetClientRect(window, &actual) && actual.right > 0 && actual.bottom > 0, "client bounds");
    const auto rect_table = image + 0x1142000;
    Put(native_window + 4, rect_table); Put(rect_table + 0x1c, image + 0x25167);
    const RECT logical{0, 0, actual.right / 2, actual.bottom / 2};
    Put(native_window + 8, logical); Put(native_window + 0x64, std::uint32_t{2});
    Put(image + 0x16a2fdc, actual.right); Put(image + 0x16a2fe0, actual.bottom);
    Put(image + 0x16a7bfc, native_window); Put(image + 0x16a7c00, reinterpret_cast<std::uintptr_t>(manager.data()));
    const auto input_manager = image + 0x1145000;
    Put(image + 0x16ac67c, input_manager); Put(input_manager + 0x10, image + 0x2112); Put(input_manager + 0x18, image + 0x4e0d);
    wm::NativeUi ui; active_ui = &ui;
    Check(!ui.Bind(window) && !ui.Available(), "unreviewed image cannot bind native UI");
    wm::NativeUiTestAccess::Bind(ui, window);
    wm::NativeUiState state;
    const POINT point{actual.right / 2, actual.bottom / 2};
    Check(ui.Snapshot(point, state) && state.available && !state.keyboard_owned && !state.pointer_owned, "unowned game input");
    Check(last_hit.x == point.x * logical.right / actual.right && last_hit.y == point.y * logical.bottom / actual.bottom, "native UI coordinate scale");
    text = true; const auto before_text = hits;
    Check(ui.Snapshot(point, state) && state.keyboard_owned && state.pointer_owned && hits == before_text, "native text predicate suppresses movement and drag before hit testing");
    text = false; focused = control.data();
    for (const std::uint32_t kind : {5U, 6U, 14U}) {
        Put(reinterpret_cast<std::uintptr_t>(focused) + 0x3b8, kind);
        Check(ui.Snapshot(point, state) && state.keyboard_owned && state.pointer_owned, "focused text kinds suppress without active-HUD predicate");
    }
    focused = nullptr;
    Put(image + 0x16a9ee8, std::uintptr_t{1});
    Check(ui.Snapshot(point, state) && state.keyboard_owned && state.pointer_owned, "native modal suppresses both input paths");
    Put(image + 0x16a9ee8, std::uintptr_t{0}); Put(native_window + 0x28, std::uintptr_t{1});
    Check(ui.Snapshot(point, state) && state.keyboard_owned && state.pointer_owned, "inventory drag retains input ownership");
    Put(native_window + 0x28, std::uintptr_t{0});
    for (const std::uint32_t mask : {2U, 4U, 8U}) {
        Put(reinterpret_cast<std::uintptr_t>(manager.data()) + 0x28, mask);
        Check(ui.Snapshot(point, state) && (mask == 2 ? state.keyboard_owned : state.pointer_owned), "native input-inhibit bits respected");
    }
    Put(reinterpret_cast<std::uintptr_t>(manager.data()) + 0x28, std::uint32_t{0});
    hit = true;
    Check(ui.Snapshot(point, state) && state.pointer_owned && !state.keyboard_owned, "native UI/map hit owns pointer only");
    hit = false; Put(image + 0x16a2dd0, std::uint8_t{1});
    Check(ui.Snapshot(point, state) && state.camera_gesture && !state.keyboard_owned && !state.pointer_owned, "camera gesture is separate from movement UI ownership");
    Put(image + 0x16a2dd0, std::uint8_t{0});
    Check(ui.Snapshot({-1, 0}, state) && state.pointer_owned && !state.keyboard_owned, "leaving window suppresses drag without taking keyboard UI ownership");
    std::atomic<bool> result{true}; const auto before_foreign = hits;
    std::thread foreign([&] { wm::NativeUiState other; result = ui.Snapshot(point, other); }); foreign.join();
    Check(!result && hits == before_foreign, "foreign thread never calls native UI");
    reenter = true; Check(ui.Snapshot(point, state), "outer query survives blocked reentry"); reenter = false;
    change_scene = true;
    Check(!ui.Snapshot(point, state) && !state.available && state.keyboard_owned && state.pointer_owned, "native window transition inside hit callback fails closed");
    change_scene = false; Put(image + 0x16a7bfc, native_window);
    Check(ui.Snapshot(point, state), "new valid snapshot can recover after transition");
    Put(rect_table + 0x1c, image + 0x25168);
    Check(!ui.Snapshot(point, state), "unverified geometry getter is unavailable");
    Put(rect_table + 0x1c, image + 0x25167); Put(image + 0x16a2fdc, LONG{0});
    Check(!ui.Snapshot(point, state), "invalid native resolution cannot invent coordinates");
    Put(image + 0x16a2fdc, actual.right); Put(native_window + 0x64, std::uint32_t{1});
    Check(!ui.Snapshot(point, state), "nonplayable native scene suppresses controls");
    Put(native_window + 0x64, std::uint32_t{2});
    Put(input_manager + 0x10, image + 0x2113);
    Check(!ui.Snapshot(point, state), "foreign text predicate cannot silently reuse native UI assumptions");
    Put(input_manager + 0x10, image + 0x2112); raise_fault = true;
    Check(!ui.Snapshot(point, state) && !ui.Available() && !state.available, "native UI exception latches unavailable");
    DestroyWindow(window); VirtualFree(reinterpret_cast<void*>(image), 0, MEM_RELEASE);
    return failures ? 1 : 0;
}
