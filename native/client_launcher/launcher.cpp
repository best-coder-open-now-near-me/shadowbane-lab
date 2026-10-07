#include "platform.h"
#include "profile.h"
#include <Shellapi.h>
#include <cstdio>
#include <optional>

using namespace shadowbane::desktop;
namespace {
struct Options {
    std::filesystem::path root, report;
    std::wstring monitor;
    bool inspect{}, help{};
};
void Parse(Options& result) {
    int count = 0;
    auto raw = CommandLineToArgvW(GetCommandLineW(), &count);
    if (!raw) throw std::runtime_error("Cannot read launch arguments.");
    std::vector<std::wstring> args;
    try { for (int i = 1; i < count; ++i) args.emplace_back(raw[i]); }
    catch (...) { LocalFree(raw); throw; }
    LocalFree(raw);
    result.inspect = std::find(args.begin(), args.end(), L"--inspect") != args.end();
    result.root = std::filesystem::path(ExecutablePath()).parent_path();
    std::vector<std::wstring> seen;
    for (std::size_t i = 0; i < args.size(); ++i) {
        const auto& key = args[i];
        if (std::find(seen.begin(), seen.end(), key) != seen.end())
            throw std::runtime_error("A launch option was supplied twice.");
        seen.push_back(key);
        if (key == L"--inspect") result.inspect = true;
        else if (key == L"--help") result.help = true;
        else if (key == L"--client-root" || key == L"--monitor" || key == L"--report") {
            if (++i == args.size() || args[i].empty()) throw std::runtime_error("A launch option has no value.");
            if (key == L"--client-root") result.root = args[i];
            else if (key == L"--monitor") result.monitor = args[i];
            else result.report = args[i];
        } else throw std::runtime_error("Unknown launch option. Use --help.");
    }
    result.root = std::filesystem::absolute(result.root).lexically_normal();
}
void Report(const Options& options, const std::string& status, const std::string& message,
            const std::vector<Display>& displays, DWORD process, bool markers,
            const std::optional<WindowIdentity>& window) {
    std::string text = "{\"schema_version\":1,\"launcher_version\":\"1.0.0\",\"status\":" + Json(status) +
        ",\"message\":" + Json(message) + ",\"profile\":" + Json(kProfile) +
        ",\"client_root\":" + Json(Utf8(options.root.wstring())) +
        ",\"markers_verified\":" + (markers ? "true" : "false") +
        ",\"process_id\":" + std::to_string(process) + ",\"window_handle\":" +
        std::to_string(window ? reinterpret_cast<std::uintptr_t>(window->window) : 0) + ",\"displays\":[";
    bool first = true;
    for (const auto& display : displays) {
        if (!first) text += ',';
        first = false; text += Describe(display);
    }
    text += "]}\n";
    const auto output = GetStdHandle(STD_OUTPUT_HANDLE);
    if (output && output != INVALID_HANDLE_VALUE) {
        DWORD written = 0;
        WriteFile(output, text.data(), static_cast<DWORD>(text.size()), &written, nullptr);
    }
    auto path = options.report;
    if (path.empty() && options.inspect) return;
    if (path.empty()) {
        if (options.root.empty() || !std::filesystem::is_directory(options.root)) return;
        FILETIME time{}; GetSystemTimeAsFileTime(&time);
        const auto stamp = (static_cast<unsigned long long>(time.dwHighDateTime) << 32) | time.dwLowDateTime;
        path = options.root / L"LauncherLogs" /
            (std::to_wstring(stamp) + L"-" + std::to_wstring(GetCurrentProcessId()) + L".json");
    }
    if (!path.parent_path().empty()) std::filesystem::create_directories(path.parent_path());
    Handle file(CreateFileW(path.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_NEW, FILE_ATTRIBUTE_NORMAL, nullptr));
    if (file.get() == INVALID_HANDLE_VALUE) throw std::runtime_error("Cannot create the new launch report.");
    DWORD written = 0;
    if (!WriteFile(file.get(), text.data(), static_cast<DWORD>(text.size()), &written, nullptr) ||
        written != text.size() || !FlushFileBuffers(file.get()))
        throw std::runtime_error("Cannot save the launch report.");
}
void RequireUnchangedDisplays(const std::vector<Display>& expected) {
    const auto current = Displays();
    if (current.size() != expected.size()) throw std::runtime_error("The monitor layout changed during startup.");
    for (const auto& original : expected) {
        const auto& now = SelectDisplay(current, original.device);
        if (now.current != original.current || now.left != original.left || now.top != original.top)
            throw std::runtime_error("The desktop display mode changed during startup.");
    }
}
WindowIdentity FinishStartup(HANDLE process, DWORD pid, const Display& display,
                             const std::vector<Display>& before) {
    const auto deadline = GetTickCount64() + 90000;
    std::optional<WindowIdentity> chosen;
    ULONGLONG stable_since = 0;
    std::string last_error = "No stable game window was created within 90 seconds.";
    while (GetTickCount64() < deadline) {
        if (WaitForSingleObject(process, 0) != WAIT_TIMEOUT)
            throw std::runtime_error("The client exited before desktop fullscreen was ready.");
        RequireUnchangedDisplays(before);
        const auto windows = ClientWindows(pid);
        if (windows.size() > 1) throw std::runtime_error("More than one game window was found for this process.");
        if (windows.size() == 1) {
            const auto& candidate = windows.front();
            if (!chosen || chosen->window != candidate.window || chosen->thread != candidate.thread) {
                chosen = candidate;
                ApplyDesktopFrame(*chosen, process, display);
                stable_since = 0;
            }
            try {
                VerifyDesktopFrame(*chosen, process, display);
                if (stable_since == 0) stable_since = GetTickCount64();
                if (GetTickCount64() - stable_since >= 2000) return *chosen;
            } catch (const std::runtime_error& error) {
                last_error = error.what(); stable_since = 0;
            }
        } else { chosen.reset(); stable_since = 0; }
        Sleep(100);
    }
    throw std::runtime_error(last_error);
}
}  // namespace

int WINAPI wWinMain(HINSTANCE, HINSTANCE, PWSTR, int) {
    Options options;
    std::vector<Display> displays;
    bool markers = false;
    DWORD pid = 0;
    std::optional<WindowIdentity> window;
    try {
        Parse(options);
        if (options.help) {
            const char* help = "ShadowbaneLauncher.exe [--client-root PATH] [--monitor DEVICE] "
                "[--inspect] [--report NEW_PATH]\nDefaults: client beside launcher; primary display.\n";
            DWORD written = 0; WriteFile(GetStdHandle(STD_OUTPUT_HANDLE), help,
                static_cast<DWORD>(strlen(help)), &written, nullptr);
            return 0;
        }
        if (!std::filesystem::is_directory(options.root)) throw std::runtime_error("Client directory does not exist.");
        const auto executable = options.root / kExePath;
        auto exe_lock = VerifyFile(executable, kExeSize, kExeHash);
        auto objects_lock = VerifyFile(options.root / kObjectsPath, kObjectsSize, kObjectsHash);
        markers = true;
        displays = Displays();
        const auto display = SelectDisplay(displays, options.monitor);
        std::string blocked;
        try {
            RequireNoExistingClient(executable);
            ValidateDesktop(display);
            PrepareDesktopPreferences(options.root / L"Config" / L"ArcanePref.cfg", display, false);
        }
        catch (const std::runtime_error& error) { blocked = error.what(); }
        if (options.inspect) {
            Report(options, blocked.empty() ? "preflight_ready" : "preflight_blocked", blocked,
                   displays, 0, markers, window);
            return blocked.empty() ? 0 : 2;
        }
        if (!blocked.empty()) throw std::runtime_error(blocked);
        // One launcher per physical client directory; marker file ID handles path aliases.
        BY_HANDLE_FILE_INFORMATION identity{};
        if (!GetFileInformationByHandle(exe_lock.get(), &identity)) throw std::runtime_error("Cannot identify client file.");
        const auto mutex_name = L"Local\\ShadowbaneDesktop-" + std::to_wstring(identity.dwVolumeSerialNumber) +
            L"-" + std::to_wstring(identity.nFileIndexHigh) + L"-" + std::to_wstring(identity.nFileIndexLow);
        Handle mutex(CreateMutexW(nullptr, FALSE, mutex_name.c_str()));
        if (!mutex.get()) throw std::runtime_error("Cannot coordinate client startup.");
        const auto ownership = WaitForSingleObject(mutex.get(), 0);
        if (ownership != WAIT_OBJECT_0 && ownership != WAIT_ABANDONED)
            throw std::runtime_error("Another launcher is already starting this client.");
        RequireNoExistingClient(executable);
        RequireUnchangedDisplays(displays);
        PrepareDesktopPreferences(options.root / L"Config" / L"ArcanePref.cfg", display);
        auto command = Arguments(executable.wstring(), display);
        auto environment = ChildEnvironment();
        STARTUPINFOW startup{}; startup.cb = sizeof(startup);
        PROCESS_INFORMATION created{};
        if (!CreateProcessW(executable.c_str(), command.data(), nullptr, nullptr, FALSE,
                CREATE_UNICODE_ENVIRONMENT, environment.data(), options.root.c_str(), &startup, &created))
            throw std::runtime_error("Windows could not start the verified client (error " +
                std::to_string(GetLastError()) + ").");
        Handle process(created.hProcess), thread(created.hThread);
        pid = created.dwProcessId;
        window = FinishStartup(process.get(), pid, display, displays);
        RequireUnchangedDisplays(displays);
        Report(options, "desktop_fullscreen_ready", "Physical client area and unchanged desktop mode verified.",
               displays, pid, markers, window);
        ReleaseMutex(mutex.get());
        return 0;
    } catch (const std::exception& error) {
        const auto message = std::string(error.what()) + (pid ? " The client was left running; it was not terminated." : "");
        try { Report(options, "failed", message, displays, pid, markers, window); } catch (...) {}
        if (!options.inspect) MessageBoxA(nullptr, message.c_str(), "Shadowbane startup", MB_OK | MB_ICONERROR);
        return 1;
    }
}
