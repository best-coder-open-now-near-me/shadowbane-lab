#include "movement_native_ui.h"
#include "movement_native_image.h"
#include <cstring>
namespace wonderbane::extension::movement {
namespace {
template<class T> bool UiRead(std::uintptr_t address, T& out) noexcept {
    if (address < 0x10000 || address > 0x7fff0000 - sizeof(T)) { return false; }
    __try { std::memcpy(&out, reinterpret_cast<const void*>(address), sizeof(T)); return true; }
    __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
}
NativePointResult NativeClientPoint(std::uintptr_t base, std::uintptr_t native_window,
    HWND window, POINT client, POINT& native) noexcept {
    native = {}; RECT actual{}, logical{};
    std::uintptr_t rectangle_table = 0, getter = 0;
    std::int32_t resolution_x = 0, resolution_y = 0;
    if (!GetClientRect(window, &actual) || actual.right <= actual.left || actual.bottom <= actual.top
        || !UiRead(native_window + 4, rectangle_table) || !UiRead(rectangle_table + 0x1c, getter)
        || getter != base + 0x25167 || !UiRead(native_window + 8, logical)
        || !UiRead(base + 0x16a2fdc, resolution_x) || !UiRead(base + 0x16a2fe0, resolution_y)) { return NativePointResult::unavailable; }
    const auto width = static_cast<std::int64_t>(logical.right) - logical.left;
    const auto height = static_cast<std::int64_t>(logical.bottom) - logical.top;
    if (width <= 0 || height <= 0 || width > 32768 || height > 32768
        || resolution_x <= 0 || resolution_y <= 0 || resolution_x > 32768 || resolution_y > 32768) { return NativePointResult::unavailable; }
    if (client.x < actual.left || client.x >= actual.right || client.y < actual.top || client.y >= actual.bottom) { return NativePointResult::outside; }
    // The sealed rectangle getter copies native_window+8. Native mouse dispatch
    // divides physical coordinates by resolution/native-rectangle extent, then
    // converts to integer. No desktop cursor mutation or guessed terrain plane.
    const auto x = static_cast<double>(client.x) * static_cast<double>(width) / resolution_x;
    const auto y = static_cast<double>(client.y) * static_cast<double>(height) / resolution_y;
    if (x < 0 || y < 0 || x >= width || y >= height) { return NativePointResult::outside; }
    native = {static_cast<LONG>(x), static_cast<LONG>(y)}; return NativePointResult::valid;
}
bool NativeUi::Bind(HWND window) noexcept {
    DWORD pid = 0; const auto thread = GetWindowThreadProcessId(window, &pid);
    if (bound_ || querying_ || !thread || thread != GetCurrentThreadId() || pid != GetCurrentProcessId()
        || !VerifyNativeMovementImage(base_)) { return false; }
    window_ = window; thread_ = thread;
    calls_.text = reinterpret_cast<decltype(calls_.text)>(base_ + 0x453c40);
    calls_.focused = reinterpret_cast<decltype(calls_.focused)>(base_ + 0x77f8b0);
    calls_.hit = reinterpret_cast<decltype(calls_.hit)>(base_ + 0x7834f0);
    bound_ = true; return true;
}
bool NativeUi::Current(std::uintptr_t native_window) const noexcept {
    DWORD pid = 0; std::uintptr_t actual = 0; std::uint32_t mode = 0;
    return Available() && GetCurrentThreadId() == thread_
        && GetWindowThreadProcessId(window_, &pid) == thread_ && pid == GetCurrentProcessId()
        && UiRead(base_ + 0x16a7bfc, actual) && actual && actual == native_window
        && UiRead(actual + 0x64, mode) && mode == 2;
}
bool NativeUi::Gates(std::uintptr_t native_window, bool& keyboard, bool& pointer, bool& camera) {
    std::uintptr_t modal = 0, drag = 0, manager = 0, input = 0, predicate = 0, text_callback = 0;
    std::uint32_t inhibited = 0; std::uint8_t gesture = 0;
    if (!Current(native_window) || !UiRead(base_ + 0x16a9ee8, modal) || !UiRead(native_window + 0x28, drag)
        || !UiRead(base_ + 0x16a7c00, manager) || !manager || !UiRead(manager + 0x28, inhibited)
        || !UiRead(base_ + 0x16a2dd0, gesture)
        || !UiRead(base_ + 0x16ac67c, input) || !input
        || !UiRead(input + 0x10, predicate) || predicate != base_ + 0x2112
        || !UiRead(input + 0x18, text_callback) || text_callback != base_ + 0x4e0d) { return false; }
    keyboard = modal || drag || (inhibited & (1U << 1));
    pointer = modal || drag || (inhibited & ((1U << 2) | (1U << 3)));
    camera = gesture != 0;
    if (calls_.text()) { keyboard = pointer = true; }
    if (!Current(native_window)) { return false; }
    // The native predicate checks the active HUD first. Also inspect the native
    // focused control directly, so a transient HUD change cannot expose text keys.
    const auto focused = reinterpret_cast<std::uintptr_t>(calls_.focused(reinterpret_cast<void*>(native_window)));
    if (!Current(native_window)) { return false; }
    if (focused) {
        std::uint32_t kind = 0;
        if (!UiRead(focused + 0x3b8, kind)) { return false; }
        if (kind == 5 || kind == 6 || kind == 14) { keyboard = pointer = true; }
    }
    return true;
}
bool NativeUi::Run(POINT client, NativeUiState& out) {
    NativeUiState next{};
    if (!UiRead(base_ + 0x16a7bfc, next.native_window)
        || !Gates(next.native_window, next.keyboard_owned, next.pointer_owned, next.camera_gesture)) { return false; }
    const auto point = NativeClientPoint(base_, next.native_window, window_, client, next.native_point);
    if (point == NativePointResult::unavailable) { return false; }
    if (point == NativePointResult::outside) { next.pointer_owned = true; }
    else if (!next.pointer_owned) {
        // Native top-level hit testing respects visibility, UI rectangles,
        // transparent HUDs and their actual child hit tests, including world map.
        next.pointer_owned = calls_.hit(reinterpret_cast<void*>(next.native_window), next.native_point.x, next.native_point.y) != nullptr;
    }
    bool keyboard = true, pointer = true, camera = false;
    if (!Gates(next.native_window, keyboard, pointer, camera)) { return false; }
    next.keyboard_owned = next.keyboard_owned || keyboard;
    next.pointer_owned = next.pointer_owned || pointer;
    next.camera_gesture = next.camera_gesture || camera;
    next.available = true; out = next; return true;
}
bool NativeUi::CxxGuarded(POINT client, NativeUiState& out) noexcept {
    try { return Run(client, out); } catch (...) { faulted_ = true; return false; }
}
bool NativeUi::Guarded(POINT client, NativeUiState& out) noexcept {
    __try { return CxxGuarded(client, out); }
    __except(EXCEPTION_EXECUTE_HANDLER) { faulted_ = true; return false; }
}
bool NativeUi::Snapshot(POINT client, NativeUiState& out) noexcept {
    out = {};
    if (!Available() || querying_ || GetCurrentThreadId() != thread_) { return false; }
    querying_ = true; const bool ok = Guarded(client, out); querying_ = false;
    if (!ok) { out = {}; } return ok;
}
}
