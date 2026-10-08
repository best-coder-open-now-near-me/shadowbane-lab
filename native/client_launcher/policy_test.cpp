#include "policy.h"
#include "preferences.h"
#include <Windows.h>
#include <Shellapi.h>
#include <iostream>

using namespace shadowbane::desktop;

void Check(bool value, const char* message) {
    if (!value) throw std::runtime_error(message);
}
template<class Action> void Reject(Action action) {
    bool rejected = false;
    try { action(); } catch (const std::runtime_error&) { rejected = true; }
    Check(rejected, "Expected invalid startup policy to be rejected");
}
int main() {
    try {
        const Mode normal{2560, 1440, 144, 32, 0};
        const Display primary{L"\\\\.\\DISPLAY1", 0, 0, true, normal, normal};
        const Display secondary{L"\\\\.\\DISPLAY2", -1920, 0, false,
            {1920, 1080, 60, 32, 0}, {1920, 1080, 60, 32, 0}};
        const std::vector<Display> displays{primary, secondary};
        Check(SelectDisplay(displays, L"").device == primary.device, "Primary monitor selection");
        Check(SelectDisplay(displays, L"\\\\.\\display2").left == -1920, "Negative monitor origin");
        Reject([&] { SelectDisplay(displays, L"missing"); });
        Reject([&] { SelectDisplay({primary, primary}, L""); });
        auto changed = primary;
        changed.current = {800, 600, 60, 32, 0};
        Reject([&] { ValidateDesktop(changed); });
        changed = primary; changed.current.refresh = 60;
        Reject([&] { ValidateDesktop(changed); });
        changed = primary; changed.desktop.bits = 16;
        Reject([&] { ValidateDesktop(changed); });
        changed = primary; changed.current = changed.desktop = {0, 0, 60, 32, 0};
        Reject([&] { ValidateDesktop(changed); });
        Check(DpiLayer(L"") == L"HIGHDPIAWARE", "Default DPI policy");
        Check(DpiLayer(L"~ WIN7RTM DPIUNAWARE GDIDPISCALING HIGHDPIAWARE") ==
            L"~ WIN7RTM HIGHDPIAWARE", "Preserve unrelated compatibility flags");
        Check(DpiLayer(DpiLayer(L"WIN7RTM")) == DpiLayer(L"WIN7RTM"), "DPI policy is idempotent");
        for (const auto& value : {std::wstring(L"C:\\Games With Spaces\\sb.exe"),
            std::wstring(L"C:\\Unicode-\u03A9\\"), std::wstring(L"a\\\"b"), std::wstring()}) {
            const auto command = L"program " + Quote(value);
            int argc = 0;
            auto argv = CommandLineToArgvW(command.c_str(), &argc);
            Check(argv != nullptr && argc == 2, "Quoted argument count");
            const bool matched = argv[1] == value;
            LocalFree(argv);
            Check(matched, "Windows argument round-trip");
        }
        const auto command = Arguments(L"C:\\Games With Spaces\\sb.exe", primary);
        int argc = 0;
        auto argv = CommandLineToArgvW(command.c_str(), &argc);
        Check(argv && argc == 1 && std::wstring(argv[0]) == L"C:\\Games With Spaces\\sb.exe",
            "No unverified display switches are passed to the executable");
        LocalFree(argv);
        const std::string original = "# user preferences\r\nRESOLUTION= 800 600 \t([Width] [Height])\r\n"
            "FULLSCREEN= TRUE\r\nREFRESH= -1\r\nVIDEOSETTINGSVALIDATION= 800x600@-1Hz\r\n"
            "MUSIC= FALSE\r\nKEY= user hotkey\r\nCUSTOM= \xe9\r\n";
        const auto updated = DesktopPreferences(original, primary);
        Check(updated.find("RESOLUTION= 2560 1440 \t([Width] [Height])\r\n") != std::string::npos,
            "Update resolution while preserving annotation and CRLF");
        Check(updated.find("FULLSCREEN= FALSE\r\n") != std::string::npos, "Select the actual windowed renderer");
        Check(updated.find("REFRESH= 144\r\n") != std::string::npos, "Use current refresh metadata");
        Check(updated.find("VIDEOSETTINGSVALIDATION= 2560x1440@144Hz\r\n") != std::string::npos,
            "Keep the client's validation stamp consistent");
        Check(updated.ends_with("MUSIC= FALSE\r\nKEY= user hotkey\r\nCUSTOM= \xe9\r\n"),
            "Unrelated settings and non-ASCII bytes remain unchanged");
        Check(DesktopPreferences(updated, primary) == updated, "Preferences update is idempotent");
        Check(DesktopPreferences("MUSIC= FALSE", primary).starts_with("MUSIC= FALSE\nRESOLUTION="),
            "Append missing display keys without losing existing data");
        Reject([&] { DesktopPreferences("FULLSCREEN= TRUE\nFULLSCREEN= FALSE\n", primary); });
        Reject([&] { DesktopPreferences(std::string("a\0b", 3), primary); });
        std::cout << "Desktop startup policy checks passed.\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n'; return 1;
    }
}
