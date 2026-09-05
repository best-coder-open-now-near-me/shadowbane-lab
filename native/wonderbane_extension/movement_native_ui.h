#pragma once
#include <Windows.h>
#include <cstdint>
namespace wonderbane::extension::movement {
enum class NativePointResult { valid, outside, unavailable };
// Exact native mouse-event coordinate conversion, shared by UI hit testing and
// terrain unprojection. Call only with the authenticated image/window binding.
NativePointResult NativeClientPoint(std::uintptr_t base, std::uintptr_t native_window,
    HWND client_window, POINT client_point, POINT& native_point) noexcept;
struct NativeUiState {
    bool available = false;
    bool keyboard_owned = true;
    bool pointer_owned = true;
    bool camera_gesture = false;
    std::uintptr_t native_window = 0;
    POINT native_point{};
};
class NativeUi {
public:
    bool Bind(HWND) noexcept;
    bool Snapshot(POINT client_point, NativeUiState&) noexcept;
    bool Available() const noexcept { return bound_ && !faulted_; }
private:
    struct Calls {
        bool (__cdecl* text)() = nullptr;
        void* (__thiscall* focused)(void*) = nullptr;
        void* (__thiscall* hit)(void*, int, int) = nullptr;
    } calls_{};
    bool Current(std::uintptr_t) const noexcept;
    bool Gates(std::uintptr_t, bool&, bool&, bool&);
    bool Run(POINT, NativeUiState&);
    bool CxxGuarded(POINT, NativeUiState&) noexcept;
    bool Guarded(POINT, NativeUiState&) noexcept;
    HWND window_ = nullptr;
    DWORD thread_ = 0;
    std::uintptr_t base_ = 0;
    bool bound_ = false, faulted_ = false, querying_ = false;
    friend struct NativeUiTestAccess;
};
}
