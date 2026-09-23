#include "movement_settings.h"
#include "movement_wire.h"
#include <CommCtrl.h>
#include <array>
#include <cmath>
#include <cwchar>
namespace wonderbane::extension::movement {
namespace {
constexpr wchar_t preferences_key[] = L"Software\\ShadowbaneLab\\NativeMovement";
constexpr wchar_t panel_class[] = L"WonderBane.NativeMovement.Settings";
using Saved = wire::Settings;
using wire::Encode;
using wire::Decode;
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
    if (RegGetValueW(HKEY_CURRENT_USER, location, L"Settings", RRF_RT_REG_BINARY, nullptr, &value, &size) == ERROR_SUCCESS) {
        if (size == sizeof(value)) { (void)Decode(value, settings); }
        else if (size == 52 && value.magic == 0x57424d43 && value.version == 1) {
            // Explicit migration of the old registry value; wire v2 is not admitted.
            auto migrated = Encode(Settings{});
            std::memcpy(&migrated, &value, 52); migrated.version = 2;
            (void)Decode(migrated, settings);
        }
    }
    return settings;
}
enum Id : int { enabled = 100, keyboard, controller, drag, forward, backward, left, right,
    slot, movement_zone, camera_zone, sensitivity, invert_x, invert_y, button, threshold, apply, status, profile_list, profile_action, profile_control, profile_modifier, profile_set, profile_remove, profile_reset };
struct Panel {
    HWND window = nullptr;
    RuntimeSnapshot expected{};
    ControllerProfile draft{};
    static constexpr std::array<const wchar_t*, 3> action_names{L"Move (camera-relative)", L"Look (native camera)", L"Cancel movement / route"};
    static constexpr std::array<const wchar_t*, 18> control_names{L"Left stick", L"Right stick", L"A", L"B", L"X", L"Y",
        L"D-pad up", L"D-pad down", L"D-pad left", L"D-pad right", L"Start", L"Back", L"Left stick press", L"Right stick press",
        L"Left shoulder", L"Right shoulder", L"Left trigger", L"Right trigger"};
    static constexpr std::array<const wchar_t*, 4> modifier_names{L"Base", L"Left shoulder", L"Right shoulder", L"Both shoulders"};
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
    void RefreshProfile(int selected = -1) noexcept {
        SendMessageW(Item(profile_list), LB_RESETCONTENT, 0, 0);
        for (const auto& b : draft.bindings) {
            if (b.action == ControllerAction::none) { break; }
            wchar_t label[200]{};
            swprintf_s(label, L"%s / %s: %s", control_names[static_cast<unsigned>(b.control) - 1],
                modifier_names[b.modifiers], action_names[static_cast<unsigned>(b.action) - 1]);
            SendMessageW(Item(profile_list), LB_ADDSTRING, 0, reinterpret_cast<LPARAM>(label));
        }
        SendMessageW(Item(profile_list), LB_SETCURSEL, selected, 0);
    }
    void SelectProfile() noexcept {
        const auto selected = SendMessageW(Item(profile_list), LB_GETCURSEL, 0, 0);
        if (selected < 0 || selected >= static_cast<LRESULT>(draft.bindings.size())) { return; }
        const auto& b = draft.bindings[static_cast<std::size_t>(selected)];
        SendMessageW(Item(profile_action), CB_SETCURSEL, static_cast<unsigned>(b.action) - 1, 0);
        SendMessageW(Item(profile_control), CB_SETCURSEL, static_cast<unsigned>(b.control) - 1, 0);
        SendMessageW(Item(profile_modifier), CB_SETCURSEL, b.modifiers, 0);
    }
    void EditProfile(bool remove) noexcept {
        auto selected = SendMessageW(Item(profile_list), LB_GETCURSEL, 0, 0);
        const auto count = SendMessageW(Item(profile_list), LB_GETCOUNT, 0, 0);
        if (remove) {
            if (selected < 0 || selected >= count) { return; }
            for (auto i = static_cast<std::size_t>(selected); i + 1 < draft.bindings.size(); ++i) { draft.bindings[i] = draft.bindings[i + 1]; }
            draft.bindings.back() = {}; RefreshProfile(); return;
        }
        if (selected < 0) { selected = count; }
        if (selected >= static_cast<LRESULT>(draft.bindings.size())) { Text(status, L"The controller profile is full. Select a row to replace or unbind."); return; }
        const auto action = SendMessageW(Item(profile_action), CB_GETCURSEL, 0, 0);
        const auto control = SendMessageW(Item(profile_control), CB_GETCURSEL, 0, 0);
        const auto modifier = SendMessageW(Item(profile_modifier), CB_GETCURSEL, 0, 0);
        if (action < 0 || action >= 3 || control < 0 || control >= 18 || modifier < 0 || modifier >= 4) { return; }
        const bool vector = control < 2;
        if (vector != (action < 2)) { Text(status, L"Move and look require a stick. Cancel requires a button or trigger."); return; }
        draft.bindings[static_cast<std::size_t>(selected)] = {static_cast<ControllerAction>(action + 1),
            static_cast<ControllerControl>(control + 1), static_cast<std::uint8_t>(modifier)};
        RefreshProfile(); Text(status, L"Binding edited. Apply and save validates the complete profile before activation.");
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
        add(WC_STATICW, L"Controller action bindings", 0, 0, 560, 16, 400, 22);
        add(WC_LISTBOXW, L"", LBS_NOTIFY | WS_BORDER | WS_VSCROLL | WS_TABSTOP, profile_list, 560, 45, 420, 180);
        add(WC_STATICW, L"Action", 0, 0, 560, 239, 190, 18);
        add(WC_COMBOBOXW, L"", CBS_DROPDOWNLIST | WS_TABSTOP, profile_action, 560, 260, 420, 100);
        for (const auto* label : action_names) { SendMessageW(Item(profile_action), CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(label)); }
        add(WC_STATICW, L"Physical control", 0, 0, 560, 298, 190, 18);
        add(WC_COMBOBOXW, L"", CBS_DROPDOWNLIST | WS_TABSTOP | WS_VSCROLL, profile_control, 560, 319, 200, 200);
        for (const auto* label : control_names) { SendMessageW(Item(profile_control), CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(label)); }
        add(WC_STATICW, L"Shoulder combination", 0, 0, 780, 298, 200, 18);
        add(WC_COMBOBOXW, L"", CBS_DROPDOWNLIST | WS_TABSTOP, profile_modifier, 780, 319, 200, 130);
        for (const auto* label : modifier_names) { SendMessageW(Item(profile_modifier), CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(label)); }
        SendMessageW(Item(profile_action), CB_SETCURSEL, 0, 0);
        SendMessageW(Item(profile_control), CB_SETCURSEL, 0, 0);
        SendMessageW(Item(profile_modifier), CB_SETCURSEL, 0, 0);
        add(WC_BUTTONW, L"Add / replace row", BS_PUSHBUTTON | WS_TABSTOP, profile_set, 560, 366, 150, 30);
        add(WC_BUTTONW, L"Unbind row", BS_PUSHBUTTON | WS_TABSTOP, profile_remove, 720, 366, 120, 30);
        add(WC_BUTTONW, L"Reset defaults", BS_PUSHBUTTON | WS_TABSTOP, profile_reset, 850, 366, 130, 30);
        add(WC_STATICW, L"Select a row to edit; adding clears the selection.\nBase applies unless the exact held shoulder combination has a binding.\nUse a shoulder either as a modifier or an action button.\nCancel stops movement and navigation; routes never auto-resume.\nProfiles apply together. Release all controls after Apply.", 0, 0, 560, 415, 420, 105);
        draft = expected.settings.controller_profile; RefreshProfile();
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
        next.controller_profile = draft;
        if (!ValidControllerProfile(draft)) {
            Text(status, L"Binding conflict: use one action per control/shoulder combination,\none stick per vector action, and no action on a shoulder used as a modifier."); return;
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
                const auto id = GetDlgCtrlID(child);
                if (id == IDCANCEL) { DestroyWindow(panel->window); }
                else if (id == profile_set) { panel->EditProfile(false); }
                else if (id == profile_remove) { panel->EditProfile(true); }
                else if (id == profile_reset) { panel->draft = ControllerProfile{}; panel->RefreshProfile(); }
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
            if (message == WM_COMMAND && LOWORD(wp) == profile_list && HIWORD(wp) == LBN_SELCHANGE) { panel->SelectProfile(); return 0; }
            if (message == WM_COMMAND && HIWORD(wp) == BN_CLICKED) {
                if (LOWORD(wp) == profile_set) { panel->EditProfile(false); return 0; }
                if (LOWORD(wp) == profile_remove) { panel->EditProfile(true); return 0; }
                if (LOWORD(wp) == profile_reset) { panel->draft = ControllerProfile{}; panel->RefreshProfile(); return 0; }
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
    RECT bounds{0, 0, 1000, 585}; AdjustWindowRectEx(&bounds, style, FALSE, WS_EX_CONTROLPARENT);
    const auto window = CreateWindowExW(WS_EX_CONTROLPARENT, panel_class, L"WonderBane movement controls", style,
        CW_USEDEFAULT, CW_USEDEFAULT, bounds.right - bounds.left, bounds.bottom - bounds.top,
        expected.window, nullptr, klass.hInstance, &panel);
    if (!window) { return false; }
    panel.show(window, SW_SHOW); panel.foreground(window); SetFocus(panel.Item(enabled)); return true;
}
}
