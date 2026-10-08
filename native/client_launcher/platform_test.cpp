#include "platform.h"
#include <fstream>
#include <iostream>

using namespace shadowbane::desktop;
void Check(bool value, const char* message) { if (!value) throw std::runtime_error(message); }
template<class Action> void Reject(Action action) {
    bool rejected = false;
    try { action(); } catch (const std::runtime_error&) { rejected = true; }
    Check(rejected, "Expected operation to reject invalid input");
}
int main() {
    HWND window = nullptr;
    std::filesystem::path file;
    bool created_file = false;
    try {
        SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);
        Check(!Displays().empty(), "A display can be inspected");
        Check(!ExecutablePath().empty(), "Executable path available");
        Check(Utf8(L"\u03a9") == "\xce\xa9", "Unicode encoding");
        Check(Json("quote\"slash\\\n") == "\"quote\\\"slash\\\\\\u000a\"", "JSON escapes controls");
        SetEnvironmentVariableW(L"__COMPAT_LAYER", L"DPIUNAWARE WIN7RTM");
        SetEnvironmentVariableW(L"SB_LAUNCHER_TEST", L"\u03a9 test");
        const auto environment = ChildEnvironment();
        bool layer = false, value = false;
        for (const wchar_t* p = environment.data(); *p; p += wcslen(p) + 1) {
            layer |= std::wstring_view(p) == L"__COMPAT_LAYER=WIN7RTM HIGHDPIAWARE";
            value |= std::wstring_view(p) == L"SB_LAUNCHER_TEST=\u03a9 test";
        }
        Check(layer && value && environment.back() == 0, "Child-only environment with unrelated values retained");
        file = std::filesystem::temp_directory_path() /
            (L"shadowbane-launcher-test-" + std::to_wstring(GetCurrentProcessId()) + L".bin");
        {
            Handle fixture(CreateFileW(file.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_NEW, 0, nullptr));
            Check(fixture.get() != INVALID_HANDLE_VALUE, "Do not overwrite a pre-existing test file");
            created_file = true;
            DWORD written = 0;
            Check(WriteFile(fixture.get(), "abc", 3, &written, nullptr) && written == 3, "Write test fixture");
        }
        constexpr auto digest = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";
        {
            auto marker = VerifyFile(file, 3, digest);
            Handle writer(CreateFileW(file.c_str(), GENERIC_WRITE, FILE_SHARE_READ, nullptr,
                OPEN_EXISTING, 0, nullptr));
            Check(writer.get() == INVALID_HANDLE_VALUE && GetLastError() == ERROR_SHARING_VIOLATION,
                "Verified marker remains locked against writes");
        }
        Reject([&] { VerifyFile(file, 4, digest); });
        Reject([&] { VerifyFile(file, 3, "not-the-digest"); });
        const Mode test_mode{1920, 1080, 60, 32, 0};
        const Display test_display{L"test", 0, 0, true, test_mode, test_mode};
        {
            std::ofstream prefs(file, std::ios::binary | std::ios::trunc);
            prefs << "MUSIC= FALSE\r\nFULLSCREEN= TRUE\r\n";
        }
        PrepareDesktopPreferences(file, test_display, false);
        {
            std::ifstream prefs(file, std::ios::binary);
            const std::string text((std::istreambuf_iterator<char>(prefs)), {});
            Check(text == "MUSIC= FALSE\r\nFULLSCREEN= TRUE\r\n", "Inspection does not change preferences");
        }
        PrepareDesktopPreferences(file, test_display);
        {
            std::ifstream prefs(file, std::ios::binary);
            const std::string text((std::istreambuf_iterator<char>(prefs)), {});
            Check(text.starts_with("MUSIC= FALSE\r\nFULLSCREEN= FALSE\r\n") &&
                text.find("RESOLUTION= 1920 1080\r\n") != std::string::npos,
                "Atomic update preserves unrelated preferences");
        }
        Check(!std::filesystem::exists(file.wstring() + L".desktop-" +
            std::to_wstring(GetCurrentProcessId()) + L".tmp"), "No replacement temporary remains");
        PrepareDesktopPreferences(file, test_display);
        Reject([&] { RequireCompleteUpdate(file); });
        Check(std::filesystem::remove(file), "Remove generated fixture");
        RequireCompleteUpdate(file); file.clear();
        WNDCLASSW type{}; type.lpfnWndProc = DefWindowProcW;
        type.hInstance = GetModuleHandleW(nullptr); type.lpszClassName = L"ShadowbaneLauncherHiddenTest";
        Check(RegisterClassW(&type) != 0, "Register test window");
        window = CreateWindowExW(WS_EX_WINDOWEDGE, type.lpszClassName, L"Shadowbane",
            WS_OVERLAPPEDWINDOW, 10, 10, 200, 200, nullptr, nullptr, type.hInstance, nullptr);
        Check(window != nullptr && !IsWindowVisible(window), "Fixture stays hidden");
        const WindowIdentity identity{window, GetCurrentProcessId(), GetCurrentThreadId()};
        const Mode mode{1280, 720, 60, 32, 0};
        const Display display{L"test", -1280, 0, false, mode, mode};
        for (int pass = 0; pass < 2; ++pass) {
            ApplyDesktopFrame(identity, GetCurrentProcess(), display);
            RECT rect{}; GetClientRect(window, &rect);
            POINT origin{}; ClientToScreen(window, &origin);
            Check(rect.right == 1280 && rect.bottom == 720 && origin.x == -1280 && origin.y == 0,
                "Physical client dimensions and negative monitor origin");
            Check(!IsWindowVisible(window), "Framing does not force visibility or focus");
        }
        auto wrong = identity; ++wrong.process;
        Reject([&] { ApplyDesktopFrame(wrong, GetCurrentProcess(), display); });
        DestroyWindow(window); window = nullptr;
        Reject([&] { ApplyDesktopFrame(identity, GetCurrentProcess(), display); });
        std::cout << "Native launcher boundary checks passed.\n"; return 0;
    } catch (const std::exception& error) {
        if (window) DestroyWindow(window);
        if (created_file && !file.empty() && std::filesystem::exists(file)) std::filesystem::remove(file);
        std::cerr << error.what() << '\n'; return 1;
    }
}
