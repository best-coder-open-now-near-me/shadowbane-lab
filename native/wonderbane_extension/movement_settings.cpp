#include "movement_settings.h"
#include <CommCtrl.h>
#include <array>
#include <cmath>
#include <cwchar>
namespace wonderbane::extension::movement {
namespace {
constexpr wchar_t preferences_key[] = L"Software\\ShadowbaneLab\\NativeMovement";
constexpr wchar_t panel_class[] = L"WonderBane.NativeMovement.Settings";
struct Saved {
    std::uint32_t magic = 0x57424d43, version = 1, flags = 0;
    std::array<std::uint32_t, 4> keys{};
    std::uint32_t slot = 0;
    float movement_zone = 0, camera_zone = 0, sensitivity = 0, threshold = 0;
    std::uint32_t button = 0;
};
static_assert(sizeof(Saved) == 52);
Saved Encode(const Settings& s) noexcept {
    Saved value{};
    value.flags = (s.enabled ? 1U : 0U) | (s.keyboard ? 2U : 0U) | (s.controller ? 4U : 0U)
        | (s.drag ? 8U : 0U) | (s.invert_camera_x ? 16U : 0U) | (s.invert_camera_y ? 32U : 0U);
    for (std::size_t i = 0; i < 4; ++i) { value.keys[i] = s.keys[i]; }
    value.slot = s.controller_slot; value.movement_zone = s.movement_dead_zone;
    value.camera_zone = s.camera_dead_zone; value.sensitivity = s.camera_radians_per_second;
    value.threshold = s.drag_threshold_pixels; value.button = s.drag_button; return value;
}
bool Decode(const Saved& value, Settings& s) noexcept {
    if (value.magic != 0x57424d43 || value.version != 1 || (value.flags & ~63U) || value.button > 255) { return false; }
    Settings next{};
    next.enabled = (value.flags & 1) != 0; next.keyboard = (value.flags & 2) != 0;
    next.controller = (value.flags & 4) != 0; next.drag = (value.flags & 8) != 0;
    next.invert_camera_x = (value.flags & 16) != 0; next.invert_camera_y = (value.flags & 32) != 0;
    for (std::size_t i = 0; i < 4; ++i) {
        if (value.keys[i] > 255) { return false; } next.keys[i] = static_cast<std::uint16_t>(value.keys[i]);
    }
    next.controller_slot = value.slot; next.movement_dead_zone = value.movement_zone;
    next.camera_dead_zone = value.camera_zone; next.camera_radians_per_second = value.sensitivity;
    next.drag_threshold_pixels = value.threshold; next.drag_button = static_cast<std::uint16_t>(value.button);
    if (!ValidSettings(next)) { return false; } s = next; return true;
}
bool SaveTo(const wchar_t* location, const Settings& settings) noexcept {
    if (!ValidSettings(settings)) { return false; }
    const auto value = Encode(settings); HKEY key = nullptr;
    if (RegCreateKeyExW(HKEY_CURRENT_USER, location, 0, nullptr, 0, KEY_SET_VALUE, nullptr, &key, nullptr) != ERROR_SUCCESS) { return false; }
    const auto result = RegSetValueExW(key, L"Settings", 0, REG_BINARY, reinterpret_cast<const BYTE*>(&value), sizeof(value));
    RegCloseKey(key); return result == ERROR_SUCCESS;
}
bool Save(const Settings& settings) noexcept { return SaveTo(preferences_key, settings); }
Settings LoadFrom(const wchar_t* location) noexcept {
    Saved value{}; DWORD size = sizeof(value); Settings settings{};
    if (RegGetValueW(HKEY_CURRENT_USER, location, L"Settings", RRF_RT_REG_BINARY, nullptr, &value, &size) == ERROR_SUCCESS
        && size == sizeof(value)) { (void)Decode(value, settings); }
    return settings;
}
enum Id : int { enabled = 100, keyboard, controller, drag, forward, backward, left, right,
    slot, movement_zone, camera_zone, sensitivity, invert_x, invert_y, button, threshold, apply, status };
struct Panel {
    HWND window = nullptr;
    RuntimeSnapshot expected{};
    bool (*persist)(const Settings&) noexcept = &Save;
    decltype(&ShowWindow) show = &ShowWindow;
    decltype(&SetForegroundWindow) foreground = &SetForegroundWindow;
    HWND Add(const wchar_t* kind, const wchar_t* text, DWORD style, int id, int x, int y, int width, int height) noexcept {
        HWND child = CreateWindowExW(std::wcscmp(kind, WC_EDITW) == 0 ? WS_EX_CLIENTEDGE : 0, kind, text,
            WS_CHILD | WS_VISIBLE | style, x, y, width, height, window,
            reinterpret_cast<HMENU>(static_cast<INT_PTR>(id)), GetModuleHandleW(nullptr), nullptr);
        if (child) {
            if (std::wcscmp(kind, HOTKEY_CLASSW) == 0) { SendMessageW(child, HKM_SETRULES, 0, 0); }
            SendMessageW(child, WM_SETFONT, reinterpret_cast<WPARAM>(GetStockObject(DEFAULT_GUI_FONT)), TRUE);
            if (style & WS_TABSTOP) { SetWindowSubclass(child, &Child, 1, reinterpret_cast<DWORD_PTR>(this)); }
        }
        return child;
    }
    HWND Item(int id) const noexcept { return GetDlgItem(window, id); }
    void Text(int id, const wchar_t* text) noexcept { SetWindowTextW(Item(id), text); }
    bool Checked(int id) const noexcept { return SendMessageW(Item(id), BM_GETCHECK, 0, 0) == BST_CHECKED; }
    void CheckBox(int id, bool checked) noexcept { SendMessageW(Item(id), BM_SETCHECK, checked ? BST_CHECKED : BST_UNCHECKED, 0); }
    void SetNumber(int id, float value) noexcept {
        wchar_t text[32]{}; swprintf_s(text, L"%.3g", static_cast<double>(value)); Text(id, text);
    }
    bool ReadNumber(int id, float& value) const noexcept {
        wchar_t text[64]{}; const int length = GetWindowTextW(Item(id), text, 64);
        if (!length || length >= 63) { return false; }
        wchar_t* end = nullptr; value = std::wcstof(text, &end);
        return end && !*end && std::isfinite(value);
    }
    bool Build() noexcept {
        bool ok = true;
        const auto add = [&](const wchar_t* kind, const wchar_t* text, DWORD style, int id, int x, int y, int w, int h) {
            if (!Add(kind, text, style, id, x, y, w, h)) { ok = false; }
        };
        add(WC_STATICW, L"Native movement and camera", 0, 0, 20, 16, 530, 22);
        add(WC_BUTTONW, L"Enable controls for this client", BS_AUTOCHECKBOX | WS_TABSTOP, enabled, 20, 45, 420, 24);
        add(WC_BUTTONW, L"Keyboard movement (camera-relative)", BS_AUTOCHECKBOX | WS_TABSTOP, keyboard, 20, 81, 500, 24);
        constexpr std::array<const wchar_t*, 4> labels{L"Forward", L"Backward", L"Left", L"Right"};
        for (int n = 0; n < 4; ++n) {
            add(WC_STATICW, labels[static_cast<std::size_t>(n)], 0, 0, 20 + n * 130, 112, 110, 18);
            add(HOTKEY_CLASSW, L"", WS_TABSTOP, forward + n, 20 + n * 130, 133, 112, 25);
        }
        add(WC_BUTTONW, L"Controller (XInput gamepads)", BS_AUTOCHECKBOX | WS_TABSTOP, controller, 20, 174, 310, 24);
        add(WC_COMBOBOXW, L"", CBS_DROPDOWNLIST | WS_TABSTOP | WS_VSCROLL, slot, 340, 174, 180, 160);
        for (const auto* label : {L"Controller slot 1", L"Controller slot 2", L"Controller slot 3", L"Controller slot 4"}) {
            SendMessageW(Item(slot), CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(label));
        }
        constexpr std::array<const wchar_t*, 3> controller_labels{L"Movement dead zone", L"Camera dead zone", L"Camera radians / second"};
        for (int n = 0; n < 3; ++n) {
            add(WC_STATICW, controller_labels[static_cast<std::size_t>(n)], 0, 0, 20 + n * 175, 211, 175, 18);
            add(WC_EDITW, L"", ES_AUTOHSCROLL | WS_TABSTOP, movement_zone + n, 20 + n * 175, 233, 140, 25);
        }
        add(WC_BUTTONW, L"Invert camera horizontal", BS_AUTOCHECKBOX | WS_TABSTOP, invert_x, 20, 271, 250, 24);
        add(WC_BUTTONW, L"Invert camera vertical", BS_AUTOCHECKBOX | WS_TABSTOP, invert_y, 290, 271, 250, 24);
        add(WC_BUTTONW, L"Hold-and-drag ground steering", BS_AUTOCHECKBOX | WS_TABSTOP, drag, 20, 312, 400, 24);
        add(WC_STATICW, L"Drag button (right mouse stays camera)", 0, 0, 20, 344, 315, 18);
        add(WC_COMBOBOXW, L"", CBS_DROPDOWNLIST | WS_TABSTOP | WS_VSCROLL, button, 20, 366, 285, 160);
        for (const auto* label : {L"Left mouse (selection click preserved)", L"Middle mouse", L"Mouse button 4", L"Mouse button 5"}) {
            SendMessageW(Item(button), CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(label));
        }
        add(WC_STATICW, L"Drag threshold (pixels)", 0, 0, 340, 344, 190, 18);
        add(WC_EDITW, L"", ES_AUTOHSCROLL | WS_TABSTOP, threshold, 340, 366, 180, 25);
        add(WC_STATICW, L"Release stops movement. Manual movement takes over navigation.\nRoutes resume only with a new /go or /pve command.\nAfter focus/device loss, release keys and center both sticks to re-arm.", 0, 0, 20, 410, 520, 58);
        add(WC_STATICW, L"", 0, status, 20, 477, 520, 48);
        add(WC_BUTTONW, L"Apply and save", BS_DEFPUSHBUTTON | WS_TABSTOP, apply, 290, 535, 140, 30);
        add(WC_BUTTONW, L"Close", BS_PUSHBUTTON | WS_TABSTOP, IDCANCEL, 440, 535, 100, 30);
        const auto& s = expected.settings;
        CheckBox(enabled, s.enabled); CheckBox(keyboard, s.keyboard); CheckBox(controller, s.controller); CheckBox(drag, s.drag);
        CheckBox(invert_x, s.invert_camera_x); CheckBox(invert_y, s.invert_camera_y);
        for (int n = 0; n < 4; ++n) { SendMessageW(Item(forward + n), HKM_SETHOTKEY, s.keys[static_cast<std::size_t>(n)], 0); }
        SendMessageW(Item(slot), CB_SETCURSEL, s.controller_slot, 0);
        constexpr std::array<std::uint16_t, 4> buttons{1, 4, 5, 6};
        for (std::size_t n = 0; n < buttons.size(); ++n) {
            if (s.drag_button == buttons[n]) { SendMessageW(Item(button), CB_SETCURSEL, n, 0); }
        }
        SetNumber(movement_zone, s.movement_dead_zone); SetNumber(camera_zone, s.camera_dead_zone);
        SetNumber(sensitivity, s.camera_radians_per_second); SetNumber(threshold, s.drag_threshold_pixels);
        Text(status, expected.bindings_available ? L"Native controls available. Changes apply only to this client.\nSaved preferences are defaults for future clients." : L"Native bindings unavailable for this client. No macro fallback.");
        EnableWindow(Item(apply), expected.bindings_available);
        if (!expected.controller_api_available) {
            EnableWindow(Item(controller), FALSE);
            Text(status, L"XInput is unavailable; keyboard and drag remain configurable.\nNo controller macro fallback is used.");
        }
        return ok;
    }
    void Apply() noexcept {
        Settings next{}; next.enabled = Checked(enabled); next.keyboard = Checked(keyboard);
        next.controller = Checked(controller); next.drag = Checked(drag);
        next.invert_camera_x = Checked(invert_x); next.invert_camera_y = Checked(invert_y);
        for (int n = 0; n < 4; ++n) {
            const auto key = SendMessageW(Item(forward + n), HKM_GETHOTKEY, 0, 0);
            if ((key & ~0xff) != 0) { Text(status, L"Choose four distinct single keys; modifier combinations are not movement bindings."); return; }
            next.keys[static_cast<std::size_t>(n)] = static_cast<std::uint16_t>(key);
        }
        const auto controller_slot = SendMessageW(Item(slot), CB_GETCURSEL, 0, 0);
        const auto drag_button = SendMessageW(Item(button), CB_GETCURSEL, 0, 0);
        if (controller_slot < 0 || controller_slot >= 4 || drag_button < 0 || drag_button >= 4) { Text(status, L"Select a controller slot and drag button."); return; }
        constexpr std::array<std::uint16_t, 4> buttons{1, 4, 5, 6};
        next.controller_slot = static_cast<std::uint32_t>(controller_slot); next.drag_button = buttons[static_cast<std::size_t>(drag_button)];
        if (!ReadNumber(movement_zone, next.movement_dead_zone) || !ReadNumber(camera_zone, next.camera_dead_zone)
            || !ReadNumber(sensitivity, next.camera_radians_per_second) || !ReadNumber(threshold, next.drag_threshold_pixels)
            || !ValidSettings(next)) {
            Text(status, L"Use distinct keys; dead zones 0.05 to below 0.95, camera speed above 0 to 10,\nand drag threshold 2 to 64 pixels."); return;
        }
        const auto result = ConfigureNativeMovementControls(expected, next);
        if (result != Result::accepted) {
            Text(status, result == Result::stale ? L"This client's movement or scene changed. Close and reopen settings before applying."
                : result == Result::stop_failed ? L"Native stop failed; new movement remains blocked. Return to the client to inspect its status."
                : L"Native controls are unavailable or busy. Return to the client, then reopen settings."); return;
        }
        RuntimeSnapshot refreshed{};
        if (ReadNativeMovementControls(refreshed)) { expected = refreshed; }
        Text(status, persist(next) ? L"Applied to this client and saved. Return to the game with controls neutral."
            : L"Applied to this client, but preferences could not be saved for future clients.");
    }
    static LRESULT CALLBACK Child(HWND child, UINT message, WPARAM wp, LPARAM lp, UINT_PTR, DWORD_PTR reference) {
        auto* panel = reinterpret_cast<Panel*>(reference);
        if (message == WM_KEYDOWN && panel) {
            if (wp == VK_TAB) {
                const auto next = GetNextDlgTabItem(panel->window, child, (GetKeyState(VK_SHIFT) & 0x8000) != 0);
                if (next) { SetFocus(next); } return 0;
            }
            if (wp == VK_ESCAPE) { DestroyWindow(panel->window); return 0; }
            if (wp == VK_RETURN) {
                if (GetDlgCtrlID(child) == IDCANCEL) { DestroyWindow(panel->window); }
                else { panel->Apply(); } return 0;
            }
        }
        return DefSubclassProc(child, message, wp, lp);
    }
    static LRESULT CALLBACK Window(HWND window, UINT message, WPARAM wp, LPARAM lp) {
        auto* panel = reinterpret_cast<Panel*>(GetWindowLongPtrW(window, GWLP_USERDATA));
        if (message == WM_NCCREATE) {
            panel = static_cast<Panel*>(reinterpret_cast<CREATESTRUCTW*>(lp)->lpCreateParams);
            SetWindowLongPtrW(window, GWLP_USERDATA, reinterpret_cast<LONG_PTR>(panel)); panel->window = window;
        }
        if (panel) {
            if (message == WM_CREATE) { return panel->Build() ? 0 : -1; }
            if (message == WM_COMMAND && HIWORD(wp) == BN_CLICKED) {
                if (LOWORD(wp) == apply) { panel->Apply(); return 0; }
                if (LOWORD(wp) == IDCANCEL) { DestroyWindow(window); return 0; }
            }
            if (message == WM_NCDESTROY) { panel->window = nullptr; }
        }
        return DefWindowProcW(window, message, wp, lp);
    }
};
Panel panel;
}
Settings LoadMovementPreferences() noexcept { return LoadFrom(preferences_key); }
bool ShowMovementSettings(const RuntimeSnapshot& expected) noexcept {
    DWORD pid = 0;
    if (!expected.window || GetWindowThreadProcessId(expected.window, &pid) != GetCurrentThreadId()
        || pid != expected.process.process_id || pid != GetCurrentProcessId()) { return false; }
    if (panel.window) { panel.show(panel.window, SW_SHOW); panel.foreground(panel.window); return true; }
    INITCOMMONCONTROLSEX init{sizeof(init), ICC_WIN95_CLASSES};
    if (!InitCommonControlsEx(&init)) { return false; }
    WNDCLASSW klass{}; klass.lpfnWndProc = &Panel::Window; klass.hInstance = GetModuleHandleW(nullptr);
    klass.lpszClassName = panel_class; klass.hCursor = LoadCursorW(nullptr, IDC_ARROW);
    klass.hbrBackground = reinterpret_cast<HBRUSH>(COLOR_BTNFACE + 1);
    if (!RegisterClassW(&klass)) {
        WNDCLASSW existing{};
        if (GetLastError() != ERROR_CLASS_ALREADY_EXISTS || !GetClassInfoW(klass.hInstance, panel_class, &existing)
            || existing.lpfnWndProc != &Panel::Window) { return false; }
    }
    panel.expected = expected;
    constexpr DWORD style = WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_CLIPCHILDREN;
    RECT bounds{0, 0, 560, 585}; AdjustWindowRectEx(&bounds, style, FALSE, WS_EX_CONTROLPARENT);
    const auto window = CreateWindowExW(WS_EX_CONTROLPARENT, panel_class, L"WonderBane movement controls", style,
        CW_USEDEFAULT, CW_USEDEFAULT, bounds.right - bounds.left, bounds.bottom - bounds.top,
        expected.window, nullptr, klass.hInstance, &panel);
    if (!window) { return false; }
    panel.show(window, SW_SHOW); panel.foreground(window); SetFocus(panel.Item(enabled)); return true;
}
}
