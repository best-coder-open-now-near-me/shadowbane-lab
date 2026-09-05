#include "movement_windows_input.h"
#include "movement_native_image.h"
#include "import_hook.h"
#include <CommCtrl.h>
#include <windowsx.h>
#include <atomic>
#include <cmath>
#include <cstring>
namespace wonderbane::extension::movement {
namespace {
std::atomic<WindowsInput*> input_owner{nullptr};
constexpr UINT_PTR subclass_id = 0x57424d56;
template<class T> bool Read(std::uintptr_t address, T& output) noexcept {
    if (address < 0x10000 || address > 0x7fff0000 - sizeof(T)) { return false; }
    __try { std::memcpy(&output, reinterpret_cast<const void*>(address), sizeof(T)); return true; }
    __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
std::uint16_t Button(UINT message, WPARAM value) noexcept {
    switch (message) {
    case WM_LBUTTONDOWN: case WM_LBUTTONUP: return VK_LBUTTON;
    case WM_RBUTTONDOWN: case WM_RBUTTONUP: return VK_RBUTTON;
    case WM_MBUTTONDOWN: case WM_MBUTTONUP: return VK_MBUTTON;
    case WM_XBUTTONDOWN: case WM_XBUTTONUP:
        return GET_XBUTTON_WPARAM(value) == XBUTTON1 ? VK_XBUTTON1 : VK_XBUTTON2;
    default: return 0;
    }
}
bool Down(UINT message) noexcept {
    return message == WM_LBUTTONDOWN || message == WM_RBUTTONDOWN
        || message == WM_MBUTTONDOWN || message == WM_XBUTTONDOWN;
}
WPARAM ButtonMask(std::uint16_t button) noexcept {
    switch (button) {
    case VK_LBUTTON: return MK_LBUTTON; case VK_RBUTTON: return MK_RBUTTON;
    case VK_MBUTTON: return MK_MBUTTON; case VK_XBUTTON1: return MK_XBUTTON1;
    case VK_XBUTTON2: return MK_XBUTTON2; default: return 0;
    }
}
float Axis(SHORT value) noexcept { return static_cast<float>(value) / (value < 0 ? 32768.0F : 32767.0F); }
}
bool NativeInputWindow(HWND& window) noexcept {
    window = nullptr; std::uintptr_t base = 0, manager = 0, native_window = 0;
    return VerifyNativeMovementImage(base) && Read(base + 0x16ac67c, manager) && manager
        && Read(manager + 4, native_window) && native_window && Read(native_window + 8, window)
        && window && IsWindow(window);
}
bool WindowsInput::Bind(HWND window) noexcept {
    std::uintptr_t manager = 0, callback = 0, native_window = 0; HWND actual = nullptr;
    if (!VerifyNativeMovementImage(base_) || !Read(base_ + 0x16ac67c, manager)
        || !manager || !Read(manager + 4, native_window) || !native_window
        || !Read(native_window + 8, actual) || actual != window || !Read(manager + 0x14, callback) || callback != base_ + 0x82f6) { return false; }
    HMODULE pinned = nullptr;
    if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_PIN,
        reinterpret_cast<LPCWSTR>(&Keyboard), &pinned)) { return false; }
    manager_ = manager; verified_ = true;
    // Load only the Windows system directory; never a game-directory DLL.
    xinput_ = LoadLibraryExW(L"xinput1_4.dll", nullptr, LOAD_LIBRARY_SEARCH_SYSTEM32);
    if (!xinput_) { xinput_ = LoadLibraryExW(L"xinput9_1_0.dll", nullptr, LOAD_LIBRARY_SEARCH_SYSTEM32); }
    if (xinput_) {
        platform_.controller = reinterpret_cast<decltype(platform_.controller)>(GetProcAddress(xinput_, "XInputGetState"));
        platform_.capabilities = reinterpret_cast<decltype(platform_.capabilities)>(GetProcAddress(xinput_, "XInputGetCapabilities"));
    }
    return BindVerified(window, reinterpret_cast<std::uint32_t*>(manager + 0x14), reinterpret_cast<KeyboardCall>(callback));
}
bool WindowsInput::BindVerified(HWND window, std::uint32_t* slot, KeyboardCall original) noexcept {
    DWORD pid = 0; const auto thread = GetWindowThreadProcessId(window, &pid);
    if (bound_ || terminal_ || !slot || !original || !callbacks_.ui || !callbacks_.safety
        || !thread || thread != GetCurrentThreadId() || pid != GetCurrentProcessId()) { return false; }
    WindowsInput* expected = nullptr;
    if (!input_owner.compare_exchange_strong(expected, this)) { return false; }
    window_ = window; thread_ = thread; key_slot_ = slot; original_ = original;
    for (std::size_t key = 0; key < original_down_.size(); ++key) {
        original_down_[key] = (platform_.key(static_cast<int>(key)) & 0x8000) != 0;
    }
    // Records are published before either hook; a failed install never makes an
    // already dispatched callback lose its original or reachable state.
    bound_ = true;
    if (!SetWindowSubclass(window_, &Window, subclass_id, reinterpret_cast<DWORD_PTR>(this))
        || ReplaceImportAddressSlot(slot, reinterpret_cast<std::uint32_t>(original),
            reinterpret_cast<std::uint32_t>(&Keyboard)) != ERROR_SUCCESS) {
        terminal_ = true; Restore(); return false;
    }
    return true;
}
bool WindowsInput::Current() const noexcept {
    DWORD pid = 0; DWORD_PTR owner = 0; std::uint32_t callback = 0; std::uintptr_t manager = 0, native_window = 0; HWND actual = nullptr;
    return bound_ && !terminal_ && GetCurrentThreadId() == thread_
        && GetWindowThreadProcessId(window_, &pid) == thread_ && pid == GetCurrentProcessId()
        && GetWindowSubclass(window_, &Window, subclass_id, &owner) && owner == reinterpret_cast<DWORD_PTR>(this)
        && Read(reinterpret_cast<std::uintptr_t>(key_slot_), callback) && callback == reinterpret_cast<std::uint32_t>(&Keyboard)
        && (!verified_ || (Read(base_ + 0x16ac67c, manager) && manager == manager_
            && Read(manager + 4, native_window) && native_window
            && Read(native_window + 8, actual) && actual == window_));
}
bool WindowsInput::Available() const noexcept { return Current(); }
bool WindowsInput::ExactFocus() const noexcept { return platform_.foreground() == window_; }
bool WindowsInput::Inside(POINT point) const noexcept {
    RECT bounds{}; return GetClientRect(window_, &bounds) && PtInRect(&bounds, point);
}
bool WindowsInput::Cursor(POINT& point) const noexcept {
    return platform_.cursor(&point) && ScreenToClient(window_, &point);
}
bool WindowsInput::Query(POINT point, NativeUiState& ui) noexcept {
    ui = {}; return Current() && callbacks_.ui(callbacks_.context, point, ui) && ui.available && Current();
}
void WindowsInput::Safety(StopReason reason, bool destroying) noexcept {
    callbacks_.safety(callbacks_.context, window_, reason, destroying);
}
void WindowsInput::Cancel(StopReason reason, bool notify) noexcept {
    const bool owned = mouse_pending_ || mouse_dragging_;
    mouse_pending_ = mouse_dragging_ = false;
    if (owned && GetCapture() == window_) { ReleaseCapture(); }
    if (notify && owned) { Safety(reason); }
}
bool WindowsInput::Configure(const Settings& settings) noexcept {
    if (!Current() || !ValidSettings(settings)) { return false; }
    Cancel(StopReason::disabled, true); settings_ = settings; device_reset_ = true;
    // Suppressed releases retain their pair across remapping/disable. Newly
    // configured held keys belong to their already delivered original down.
    for (std::size_t key = 0; key < original_down_.size(); ++key) {
        if (!suppressed_[key] && (platform_.key(static_cast<int>(key)) & 0x8000)) { original_down_[key] = true; }
    }
    return true;
}
bool WindowsInput::Key(std::uint32_t key, std::uint32_t, std::uint32_t down, std::uint32_t repeat) noexcept {
    if (key >= suppressed_.size()) { return false; }
    if (suppressed_[key]) { if (!down) { suppressed_[key] = false; } return true; }
    if (!down) { original_down_[key] = false; return false; }
    if (original_down_[key] || repeat || !settings_.enabled || !settings_.keyboard || !Current() || !ExactFocus()) { original_down_[key] = true; return false; }
    POINT point{}; NativeUiState ui{};
    if (!Cursor(point) || !Query(point, ui) || ui.keyboard_owned) {
        original_down_[key] = true; Safety(StopReason::ui); return false;
    }
    if (!controls_.ConsumesKey(static_cast<std::uint16_t>(key))) { original_down_[key] = true; return false; }
    suppressed_[key] = true; return true;
}
void __cdecl WindowsInput::Keyboard(std::uint32_t key, std::uint32_t mods, std::uint32_t down, std::uint32_t repeat) {
    auto* self = input_owner.load(std::memory_order_acquire);
    if (!self || !self->original_) { return; }
    // No input state is touched on a foreign thread. Original call-through is
    // immutable and remains valid after retirement or slot replacement.
    if (GetCurrentThreadId() != self->thread_ || self->terminal_ || self->callback_active_) {
        self->original_(key, mods, down, repeat); return;
    }
    self->callback_active_ = true;
    const bool consumed = self->Key(key, mods, down, repeat);
    self->callback_active_ = false;
    if (!consumed) { self->original_(key, mods, down, repeat); }
}
LRESULT CALLBACK WindowsInput::Window(HWND window, UINT message, WPARAM wp, LPARAM lp, UINT_PTR, DWORD_PTR reference) {
    auto* self = reinterpret_cast<WindowsInput*>(reference);
    if (!self || window != self->window_ || GetCurrentThreadId() != self->thread_ || self->terminal_) {
        return DefSubclassProc(window, message, wp, lp);
    }
    return self->Message(message, wp, lp);
}
LRESULT WindowsInput::Message(UINT message, WPARAM wp, LPARAM lp) {
    if (message == WM_NCDESTROY) {
        terminal_ = true; mouse_pending_ = mouse_dragging_ = false;
        Safety(StopReason::shutdown, true); Restore();
        return DefSubclassProc(window_, message, wp, lp);
    }
    if (message == WM_KILLFOCUS || (message == WM_ACTIVATEAPP && !wp)) {
        Cancel(StopReason::focus, false); device_reset_ = true; Safety(StopReason::focus);
    } else if (message == WM_CANCELMODE) {
        Cancel(StopReason::capture_lost, true);
    } else if (message == WM_CAPTURECHANGED && reinterpret_cast<HWND>(lp) != window_) {
        Cancel(StopReason::capture_lost, true);
    } else if (message == WM_MOUSELEAVE) {
        Cancel(StopReason::capture_lost, true);
    } else if (message == WM_DEVICECHANGE) {
        device_reset_ = true;
        if (controller_connected_ && controller_moving_ && controls_.Current().owner == Owner::manual) {
            Safety(StopReason::device_lost);
        }
        controller_connected_ = controller_moving_ = false;
    }
    const auto button = Button(message, wp);
    // A fresh down proves any release lost outside our capture already occurred.
    // Do not consume the new native pair as though it were the abandoned one.
    if (button && Down(message) && mouse_up_owned_ && !mouse_pending_ && !mouse_dragging_) {
        mouse_up_owned_ = false;
    }
    if (button && !Down(message) && mouse_up_owned_ && button == mouse_button_) {
        const bool click = mouse_pending_ && !mouse_dragging_ && ExactFocus() && Inside({GET_X_LPARAM(lp), GET_Y_LPARAM(lp)});
        NativeUiState ui{};
        const bool deliver = click && Query({GET_X_LPARAM(lp), GET_Y_LPARAM(lp)}, ui) && !ui.pointer_owned && !ui.camera_gesture;
        mouse_up_owned_ = false; mouse_pending_ = mouse_dragging_ = false;
        if (GetCapture() == window_) { ReleaseCapture(); }
        if (deliver) {
            // Deliver the original pair only after classifying an ordinary click.
            // This is never used as movement actuation or as a synthetic command.
            (void)DefSubclassProc(window_, down_message_, down_wparam_, down_lparam_);
            return DefSubclassProc(window_, message, wp, lp);
        }
        return message == WM_XBUTTONUP ? TRUE : 0;
    }
    if (button && Down(message) && !mouse_up_owned_ && settings_.enabled && settings_.drag
        && button == settings_.drag_button && button != VK_RBUTTON && Current() && ExactFocus()
        && controls_.Ready() && !GetCapture()) {
        const POINT point{GET_X_LPARAM(lp), GET_Y_LPARAM(lp)}; NativeUiState ui{};
        const WPARAM buttons = MK_LBUTTON | MK_RBUTTON | MK_MBUTTON | MK_XBUTTON1 | MK_XBUTTON2;
        if (!(wp & (buttons & ~ButtonMask(button))) && Inside(point) && Query(point, ui)
            && !ui.pointer_owned && !ui.keyboard_owned && !ui.camera_gesture) {
            mouse_button_ = button; press_ = pointer_ = point;
            down_message_ = message; down_wparam_ = wp; down_lparam_ = lp;
            mouse_pending_ = mouse_up_owned_ = true;
            SetCapture(window_);
            if (GetCapture() != window_ || !Current()) {
                mouse_pending_ = mouse_up_owned_ = false; return DefSubclassProc(window_, message, wp, lp);
            }
            TRACKMOUSEEVENT tracking{sizeof(tracking), TME_LEAVE, window_, 0}; TrackMouseEvent(&tracking);
            return message == WM_XBUTTONDOWN ? TRUE : 0;
        }
    }
    if (message == WM_MOUSEMOVE && mouse_up_owned_) {
        pointer_ = {GET_X_LPARAM(lp), GET_Y_LPARAM(lp)}; NativeUiState ui{};
        if ((mouse_pending_ || mouse_dragging_) && (!Inside(pointer_) || !ExactFocus()
            || GetCapture() != window_ || !Query(pointer_, ui) || ui.pointer_owned || ui.camera_gesture)) {
            Cancel(StopReason::capture_lost, true);
        }
        if (mouse_pending_ && std::hypot(static_cast<float>(pointer_.x - press_.x),
            static_cast<float>(pointer_.y - press_.y)) >= settings_.drag_threshold_pixels) {
            mouse_pending_ = false; mouse_dragging_ = true;
        }
        // Preserve hover/other buttons without leaking an unmatched native down.
        return DefSubclassProc(window_, message, wp & ~ButtonMask(mouse_button_), lp);
    }
    return DefSubclassProc(window_, message, wp, lp);
}
bool WindowsInput::Snapshot(CapturedInput& out) noexcept {
    out = {}; auto& input = out.input; input.tick_ms = GetTickCount64();
    if (!Current()) { return false; }
    input.exact_foreground = ExactFocus();
    for (std::size_t key = 0; key < input.keys.size(); ++key) {
        input.keys[key] = (platform_.key(static_cast<int>(key)) & 0x8000) != 0;
    }
    // Only a captured eligible gesture reaches drag interpretation.
    input.keys[settings_.drag_button] = (mouse_pending_ || mouse_dragging_) && mouse_up_owned_;
    POINT point{}; NativeUiState ui{};
    if (!Cursor(point) || !Query(point, ui)) { input.ui_owns_input = true; return false; }
    input.ui_owns_input = ui.keyboard_owned;
    input.camera_blocked = ui.camera_gesture;
    input.pointer_x = static_cast<float>(point.x); input.pointer_y = static_cast<float>(point.y);
    input.pointer_in_world = Inside(point) && !ui.pointer_owned && !ui.camera_gesture;
    input.capture_valid = GetCapture() == window_ && (mouse_pending_ || mouse_dragging_);
    if (input.keys[settings_.drag_button]) { out.press_origin = press_; }
    input.controller_slot = settings_.controller_slot;
    const bool reset = device_reset_; device_reset_ = false;
    if (settings_.controller && !reset && input.exact_foreground && platform_.controller && platform_.capabilities) {
        XINPUT_STATE state{}; XINPUT_CAPABILITIES caps{};
        input.controller_connected = platform_.capabilities(settings_.controller_slot, XINPUT_FLAG_GAMEPAD, &caps) == ERROR_SUCCESS
            && caps.Type == XINPUT_DEVTYPE_GAMEPAD && caps.SubType == XINPUT_DEVSUBTYPE_GAMEPAD
            && platform_.controller(settings_.controller_slot, &state) == ERROR_SUCCESS;
        if (input.controller_connected) {
            input.left_stick = {Axis(state.Gamepad.sThumbLX), Axis(state.Gamepad.sThumbLY)};
            input.right_stick = {Axis(state.Gamepad.sThumbRX), Axis(state.Gamepad.sThumbRY)};
        }
    }
    controller_connected_ = input.controller_connected;
    const auto direction = RadialDirection(input.left_stick, settings_.movement_dead_zone);
    controller_moving_ = input.controller_connected && (direction.x != 0 || direction.y != 0);
    return true;
}
void WindowsInput::Restore() noexcept {
    if (GetCurrentThreadId() != thread_) { return; }
    DWORD_PTR owner = 0;
    if (GetWindowSubclass(window_, &Window, subclass_id, &owner) && owner == reinterpret_cast<DWORD_PTR>(this)) {
        RemoveWindowSubclass(window_, &Window, subclass_id);
    }
    std::uintptr_t manager = 0;
    if (key_slot_ && original_ && (!verified_ || (Read(base_ + 0x16ac67c, manager) && manager == manager_))) {
        (void)ReplaceImportAddressSlot(key_slot_, reinterpret_cast<std::uint32_t>(&Keyboard), reinterpret_cast<std::uint32_t>(original_));
    }
}
void WindowsInput::Retire() noexcept {
    if (!bound_ || terminal_ || GetCurrentThreadId() != thread_) { return; }
    Cancel(StopReason::shutdown, false); terminal_ = true; Restore();
}
}
