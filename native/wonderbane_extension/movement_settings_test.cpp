#include "movement_settings.cpp"
#include <iostream>
#include <limits>
namespace wm = wonderbane::extension::movement;
namespace {
int failures = 0, applied = 0, saved = 0;
wm::RuntimeSnapshot current{};
BOOL WINAPI QuietShow(HWND, int) { return TRUE; }
BOOL WINAPI QuietForeground(HWND) { return TRUE; }
void Check(bool ok, const char* text) { if (!ok) { ++failures; std::cerr << text << '\n'; } }
}
namespace wonderbane::extension::movement {
bool ReadNativeMovementControls(RuntimeSnapshot& out) noexcept { out = current; return true; }
Result ConfigureNativeMovementControls(const RuntimeSnapshot& expected, const Settings& settings) noexcept {
    if (expected.grant != current.grant || expected.settings_revision != current.settings_revision) { return Result::stale; }
    ++applied; current.settings = settings; ++current.settings_revision; return Result::accepted;
}
}
int wmain(int argc, wchar_t** argv) {
    constexpr wchar_t test_prefix[] = L"Software\\ShadowbaneLab.NativeMovement.Test.";
    if (argc == 3 && std::wcscmp(argv[1], L"preferences-child") == 0) {
        const auto prefix_length = std::wcslen(test_prefix);
        if (std::wcsncmp(argv[2], test_prefix, prefix_length) != 0) { return 2; }
        for (const wchar_t* c = argv[2] + prefix_length; *c; ++c) {
            if ((*c < L'0' || *c > L'9') && *c != L'.') { return 2; }
        }
        const auto saved_settings = wm::LoadFrom(argv[2]);
        return saved_settings.enabled && saved_settings.controller && saved_settings.controller_slot == 3
            && saved_settings.keys == std::array<std::uint16_t, 4>{0x49, 0x4b, 0x4a, 0x4c}
            && saved_settings.invert_camera_x && saved_settings.camera_dead_zone == .3F
            && saved_settings.drag_button == 6
            && saved_settings.controller_profile.bindings[2] == wm::ControllerBinding{wm::ControllerAction::cancel_movement, wm::ControllerControl::x, 1} ? 0 : 1;
    }
    wm::Settings settings; settings.enabled = settings.controller = true; settings.controller_slot = 3;
    settings.keys = {0x49, 0x4b, 0x4a, 0x4c}; settings.invert_camera_x = true;
    settings.camera_dead_zone = .3F; settings.drag_button = 6;
    wchar_t test_key[160]{};
    swprintf_s(test_key, L"%s%lu.%llu", test_prefix, GetCurrentProcessId(), GetTickCount64());
    auto legacy = wm::Encode(settings); legacy.version = 1; HKEY legacy_key = nullptr;
    Check(RegCreateKeyExW(HKEY_CURRENT_USER, test_key, 0, nullptr, 0, KEY_SET_VALUE, nullptr, &legacy_key, nullptr) == ERROR_SUCCESS,
        "isolated old preference key created");
    Check(RegSetValueExW(legacy_key, L"Settings", 0, REG_BINARY, reinterpret_cast<const BYTE*>(&legacy), 52) == ERROR_SUCCESS,
        "exact v1 preference layout stored");
    RegCloseKey(legacy_key);
    const auto migrated = wm::LoadFrom(test_key);
    Check(migrated.keys == settings.keys && migrated.controller_slot == settings.controller_slot
        && migrated.controller_profile == wm::ControllerProfile{}, "legacy settings migrate with explicit stable profile defaults");
    settings.controller_profile.bindings[2] = {wm::ControllerAction::cancel_movement, wm::ControllerControl::x, 1};
    Check(wm::SaveTo(test_key, settings), "preferences written to isolated test key");
    wchar_t executable[MAX_PATH]{}, command[2 * MAX_PATH + 180]{};
    GetModuleFileNameW(nullptr, executable, MAX_PATH);
    swprintf_s(command, L"\"%s\" preferences-child \"%s\"", executable, test_key);
    STARTUPINFOW startup{}; startup.cb = sizeof(startup); startup.dwFlags = STARTF_USESHOWWINDOW; startup.wShowWindow = SW_HIDE;
    PROCESS_INFORMATION reader_process{};
    const bool created = CreateProcessW(executable, command, nullptr, nullptr, FALSE, CREATE_NO_WINDOW,
        nullptr, nullptr, &startup, &reader_process) != FALSE;
    Check(created, "new preference reader process starts");
    if (created) {
        const auto waited = WaitForSingleObject(reader_process.hProcess, 5000);
        DWORD result = 1;
        if (waited == WAIT_OBJECT_0) { GetExitCodeProcess(reader_process.hProcess, &result); }
        else { TerminateProcess(reader_process.hProcess, 1); WaitForSingleObject(reader_process.hProcess, 1000); }
        Check(waited == WAIT_OBJECT_0 && result == 0, "saved preferences survive a separate process restart");
        CloseHandle(reader_process.hThread); CloseHandle(reader_process.hProcess);
    }
    Check(RegDeleteKeyW(HKEY_CURRENT_USER, test_key) == ERROR_SUCCESS, "isolated preference key removed");
    auto encoded = wm::Encode(settings); wm::Settings decoded;
    Check(wm::Decode(encoded, decoded) && wm::Encode(decoded).flags == encoded.flags
        && decoded.keys == settings.keys && decoded.controller_slot == 3 && decoded.drag_button == 6,
        "versioned settings preserve configured bindings, flags and explicit controller");
    encoded.flags |= 128; Check(!wm::Decode(encoded, decoded), "unknown settings flags rejected");
    encoded = wm::Encode(settings); encoded.sensitivity = std::numeric_limits<float>::quiet_NaN();
    Check(!wm::Decode(encoded, decoded), "corrupt nonfinite preferences rejected");
    HWND owner = CreateWindowExW(0, L"STATIC", L"settings owner", WS_OVERLAPPEDWINDOW, 0, 0, 640, 480,
        nullptr, nullptr, GetModuleHandleW(nullptr), nullptr);
    Check(owner != nullptr, "settings owner created");
    current.window = owner; current.process = {GetCurrentProcessId(), 42}; current.settings = settings;
    current.settings_revision = 1; current.grant = {7, 11, wm::Owner::none, {}};
    current.bindings_available = current.controller_api_available = true;
    wm::panel.show = &QuietShow; wm::panel.foreground = &QuietForeground;
    wm::panel.persist = [](const wm::Settings&) noexcept { ++saved; return true; };
    Check(wm::ShowMovementSettings(current) && wm::panel.window, "real native settings window builds");
    RECT bounds{}; GetClientRect(wm::panel.window, &bounds);
    for (const int id : std::array<int, 26>{wm::enabled, wm::keyboard, wm::controller, wm::drag, wm::forward, wm::backward,
        wm::left, wm::right, wm::slot, wm::movement_zone, wm::camera_zone, wm::sensitivity, wm::invert_x,
        wm::invert_y, wm::button, wm::threshold, wm::apply, wm::status, IDCANCEL, wm::profile_list, wm::profile_action, wm::profile_control,
        wm::profile_modifier, wm::profile_set, wm::profile_remove, wm::profile_reset}) {
        const auto child = wm::panel.Item(id); RECT rect{}; GetWindowRect(child, &rect);
        MapWindowPoints(nullptr, wm::panel.window, reinterpret_cast<POINT*>(&rect), 2);
        // Combo drop lists extend below their collapsed control by design.
        Check(child && rect.left >= 0 && rect.top >= 0 && rect.right <= bounds.right
            && rect.bottom <= bounds.bottom, "settings controls fit inside native client area");
    }
    wm::panel.Text(wm::movement_zone, L"0.25");
    SendMessageW(wm::panel.window, WM_COMMAND, MAKEWPARAM(wm::apply, BN_CLICKED), 0);
    Check(applied == 1 && saved == 1 && current.settings.movement_dead_zone == .25F,
          "real apply reads controls, validates ticket and saves accepted settings");
    wm::panel.Text(wm::sensitivity, L"nan"); wm::panel.Apply();
    Check(applied == 1 && saved == 1, "invalid UI values cannot reach native configuration");
    wm::panel.Text(wm::sensitivity, L"2"); ++current.grant.generation; wm::panel.Apply();
    Check(applied == 1 && saved == 1, "stale settings window cannot write or save over a new owner");
    const auto window = wm::panel.window; Check(wm::ShowMovementSettings(current) && wm::panel.window == window,
        "reopening focuses existing panel without replacing unsaved ticket");
    SendMessageW(window, WM_COMMAND, MAKEWPARAM(IDCANCEL, BN_CLICKED), 0);
    Check(!wm::panel.window, "close retires the panel handle");
    Check(wm::ShowMovementSettings(current), "fresh settings ticket for action editor");
    SendMessageW(wm::panel.Item(wm::profile_list), LB_SETCURSEL, 2, 0);
    wm::panel.SelectProfile();
    SendMessageW(wm::panel.Item(wm::profile_control), CB_SETCURSEL, static_cast<unsigned>(wm::ControllerControl::y) - 1, 0);
    wm::panel.EditProfile(false);
    Check(wm::panel.draft.bindings[2].control == wm::ControllerControl::y
        && current.settings.controller_profile.bindings[2].control == wm::ControllerControl::x,
        "controller editor keeps changes local until atomic apply");
    const auto before_apply = applied; wm::panel.Apply();
    Check(applied == before_apply + 1 && current.settings.controller_profile.bindings[2].control == wm::ControllerControl::y,
        "real UI applies and saves semantic controller binding");
    SendMessageW(wm::panel.Item(wm::profile_list), LB_SETCURSEL, 2, 0); wm::panel.EditProfile(true); wm::panel.Apply();
    Check(current.settings.controller_profile.bindings[2].action == wm::ControllerAction::none, "unbind removes controller action");
    SendMessageW(wm::panel.window, WM_COMMAND, MAKEWPARAM(wm::profile_reset, BN_CLICKED), 0); wm::panel.Apply();
    Check(current.settings.controller_profile == wm::ControllerProfile{}, "reset restores stable saved action defaults");
    wm::panel.draft.bindings[1] = wm::panel.draft.bindings[0]; const auto before_invalid = applied; wm::panel.Apply();
    Check(applied == before_invalid && current.settings.controller_profile == wm::ControllerProfile{},
        "conflicting complete profile cannot reach runtime or persistence");
    DestroyWindow(wm::panel.window); DestroyWindow(owner); return failures ? 1 : 0;
}
