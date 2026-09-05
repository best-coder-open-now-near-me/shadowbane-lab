#pragma once
#include <Windows.h>
#include <Xinput.h>
#include "movement_controls.h"
#include "movement_native_ui.h"
#include <optional>
namespace wonderbane::extension::movement {
// Resolve the HWND stored by the reviewed native CreateWindow path.
// No foreground-window guessing or enumeration heuristic.
bool NativeInputWindow(HWND&) noexcept;
struct InputCallbacks {
    void* context = nullptr;
    bool (*ui)(void*, POINT, NativeUiState&) noexcept = nullptr;
    // Called synchronously on the exact HWND thread. The runtime captures the
    // current scene/grant here and defers nested stops until actuation returns.
    void (*safety)(void*, HWND, StopReason, bool destroying) noexcept = nullptr;
};
struct CapturedInput {
    Input input{};
    std::optional<POINT> press_origin;
};
// One process-pinned instance. Keyboard hook/original records remain alive after
// retirement for an already fetched callback; ordinary disable uses Configure.
class WindowsInput {
public:
    WindowsInput(const Controls& controls, InputCallbacks callbacks) noexcept
        : controls_(controls), callbacks_(callbacks) {}
    bool Bind(HWND) noexcept;
    bool Configure(const Settings&) noexcept;
    bool Snapshot(CapturedInput&) noexcept;
    void Retire() noexcept;
    bool Available() const noexcept;
private:
    using KeyboardCall = void (__cdecl*)(std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t);
    struct Platform {
        decltype(&GetForegroundWindow) foreground = &GetForegroundWindow;
        decltype(&GetAsyncKeyState) key = &GetAsyncKeyState;
        decltype(&GetCursorPos) cursor = &GetCursorPos;
        decltype(&XInputGetState) controller = nullptr;
        decltype(&XInputGetCapabilities) capabilities = nullptr;
    } platform_{};
    static void __cdecl Keyboard(std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t);
    static LRESULT CALLBACK Window(HWND, UINT, WPARAM, LPARAM, UINT_PTR, DWORD_PTR);
    bool BindVerified(HWND, std::uint32_t*, KeyboardCall) noexcept;
    bool Current() const noexcept;
    bool Query(POINT, NativeUiState&) noexcept;
    bool Key(std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t) noexcept;
    LRESULT Message(UINT, WPARAM, LPARAM);
    void Cancel(StopReason, bool notify) noexcept;
    void Safety(StopReason, bool destroying = false) noexcept;
    bool Inside(POINT) const noexcept;
    bool Cursor(POINT&) const noexcept;
    bool ExactFocus() const noexcept;
    void Restore() noexcept;
    const Controls& controls_;
    InputCallbacks callbacks_{};
    Settings settings_{};
    HWND window_ = nullptr;
    DWORD thread_ = 0;
    std::uintptr_t base_ = 0, manager_ = 0;
    std::uint32_t* key_slot_ = nullptr;
    KeyboardCall original_ = nullptr;
    HMODULE xinput_ = nullptr;
    bool bound_ = false, terminal_ = false, verified_ = false, callback_active_ = false;
    bool device_reset_ = true, controller_connected_ = false, controller_moving_ = false;
    std::array<bool, 256> suppressed_{}, original_down_{};
    bool mouse_pending_ = false, mouse_dragging_ = false, mouse_up_owned_ = false;
    std::uint16_t mouse_button_ = 0;
    UINT down_message_ = 0;
    WPARAM down_wparam_ = 0;
    LPARAM down_lparam_ = 0;
    POINT press_{}, pointer_{};
    friend struct WindowsInputTestAccess;
};
}
