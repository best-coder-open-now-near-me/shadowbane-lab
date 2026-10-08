#include "platform.h"
#include "preferences.h"
#include <bcrypt.h>
#include <dwmapi.h>
#include <shellscalingapi.h>
#include <tlhelp32.h>
#include <array>
#include <iomanip>
#include <sstream>

namespace shadowbane::desktop {
namespace {
void Require(bool ok, const char* action) {
    if (!ok) throw std::runtime_error(std::string(action) + " (Windows error " +
        std::to_string(GetLastError()) + ").");
}
Mode ReadMode(const wchar_t* device, DWORD which) {
    DEVMODEW mode{}; mode.dmSize = sizeof(mode);
    Require(EnumDisplaySettingsExW(device, which, &mode, 0) != FALSE, "Read display mode");
    return {mode.dmPelsWidth, mode.dmPelsHeight, mode.dmDisplayFrequency,
        mode.dmBitsPerPel, mode.dmDisplayOrientation};
}
struct DisplayScan { std::vector<Display> items; bool failed{}; };
BOOL CALLBACK MonitorCallback(HMONITOR monitor, HDC, LPRECT, LPARAM data) {
    auto& scan = *reinterpret_cast<DisplayScan*>(data);
    try {
        MONITORINFOEXW info{}; info.cbSize = sizeof(info);
        Require(GetMonitorInfoW(monitor, &info) != FALSE, "Read monitor bounds");
        scan.items.push_back({info.szDevice, info.rcMonitor.left, info.rcMonitor.top,
            (info.dwFlags & MONITORINFOF_PRIMARY) != 0,
            ReadMode(info.szDevice, ENUM_CURRENT_SETTINGS),
            ReadMode(info.szDevice, ENUM_REGISTRY_SETTINGS)});
        return TRUE;
    } catch (...) { scan.failed = true; return FALSE; }
}
struct WindowScan { DWORD process; std::vector<WindowIdentity> items; bool failed{}; };
BOOL CALLBACK WindowCallback(HWND window, LPARAM data) {
    auto& scan = *reinterpret_cast<WindowScan*>(data);
    DWORD pid = 0; const DWORD tid = GetWindowThreadProcessId(window, &pid);
    if (pid != scan.process || !IsWindowVisible(window) || GetWindow(window, GW_OWNER)) return TRUE;
    wchar_t title[256]{};
    GetWindowTextW(window, title, 256);
    if (std::wstring_view(title) != L"Shadowbane") return TRUE;
    try { scan.items.push_back({window, pid, tid}); }
    catch (...) { scan.failed = true; return FALSE; }
    return TRUE;
}
void VerifyIdentity(const WindowIdentity& identity, HANDLE process) {
    DWORD pid = 0;
    const DWORD tid = GetWindowThreadProcessId(identity.window, &pid);
    if (!identity.window || pid != identity.process || tid != identity.thread ||
        GetProcessId(process) != identity.process || WaitForSingleObject(process, 0) != WAIT_TIMEOUT ||
        GetWindow(identity.window, GW_OWNER) ||
        (GetWindowLongPtrW(identity.window, GWL_STYLE) & WS_CHILD) != 0) {
        throw std::runtime_error("The launched client's process/window identity changed.");
    }
}
void SetStyle(HWND window, int index, LONG_PTR value) {
    SetLastError(0);
    const auto previous = SetWindowLongPtrW(window, index, value);
    Require(previous != 0 || GetLastError() == 0, "Set client window style");
}
void HashCheck(NTSTATUS status) {
    if (status < 0) throw std::runtime_error("Windows SHA-256 failed.");
}
struct HashProvider {
    BCRYPT_ALG_HANDLE value{};
    ~HashProvider() { if (value) BCryptCloseAlgorithmProvider(value, 0); }
};
struct HashState {
    BCRYPT_HASH_HANDLE value{};
    ~HashState() { if (value) BCryptDestroyHash(value); }
};
}  // namespace

std::vector<Display> Displays() {
    DisplayScan scan;
    const auto result = EnumDisplayMonitors(nullptr, nullptr, MonitorCallback,
        reinterpret_cast<LPARAM>(&scan));
    Require(result != FALSE && !scan.failed && !scan.items.empty(), "Enumerate displays");
    return scan.items;
}
std::wstring ExecutablePath() {
    std::vector<wchar_t> path(32768);
    const auto length = GetModuleFileNameW(nullptr, path.data(), static_cast<DWORD>(path.size()));
    Require(length > 0 && length < path.size(), "Read launcher path");
    return {path.data(), length};
}
void RequireCompleteUpdate(const std::filesystem::path& journal) {
    if (std::filesystem::exists(journal))
        throw std::runtime_error("A client update is incomplete. Open the patcher and use Update / Repair.");
}
void RequireNoExistingClient(const std::filesystem::path& executable) {
    Handle snapshot(CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0));
    Require(snapshot.get() != INVALID_HANDLE_VALUE, "Enumerate running processes");
    PROCESSENTRY32W entry{}; entry.dwSize = sizeof(entry);
    Require(Process32FirstW(snapshot.get(), &entry) != FALSE, "Read running processes");
    do {
        if (!EqualName(entry.szExeFile, executable.filename().wstring())) continue;
        Handle process(OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, entry.th32ProcessID));
        if (!process.get()) throw std::runtime_error("Cannot inspect another running sb.exe. Close it first.");
        std::vector<wchar_t> path(32768); DWORD size = static_cast<DWORD>(path.size());
        Require(QueryFullProcessImageNameW(process.get(), 0, path.data(), &size) != FALSE,
            "Read running client path");
        if (std::filesystem::equivalent(std::filesystem::path(std::wstring(path.data(), size)), executable)) {
            throw std::runtime_error("This client is already running. Exit it before using the new launcher.");
        }
    } while (Process32NextW(snapshot.get(), &entry));
    Require(GetLastError() == ERROR_NO_MORE_FILES, "Finish process enumeration");
}
Handle VerifyFile(const std::filesystem::path& path, unsigned long long expected_size,
                  const char* expected_hash) {
    // Keep the read handle open through process creation; writers/deletion are excluded.
    for (auto part = path; !part.empty(); part = part.parent_path()) {
        const DWORD attributes = GetFileAttributesW(part.c_str());
        Require(attributes != INVALID_FILE_ATTRIBUTES, "Read client path attributes");
        if (attributes & FILE_ATTRIBUTE_REPARSE_POINT)
            throw std::runtime_error("Client files must not use junctions or symbolic links.");
        if (part == part.root_path()) break;
    }
    Handle file(CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL | FILE_FLAG_SEQUENTIAL_SCAN | FILE_FLAG_OPEN_REPARSE_POINT, nullptr));
    Require(file.get() != INVALID_HANDLE_VALUE, "Open client marker");
    LARGE_INTEGER size{};
    Require(GetFileSizeEx(file.get(), &size) != FALSE, "Read client marker size");
    if (size.QuadPart < 0 || static_cast<unsigned long long>(size.QuadPart) != expected_size)
        throw std::runtime_error("Client files do not match this launcher's reviewed version.");
    HashProvider algorithm;
    HashCheck(BCryptOpenAlgorithmProvider(&algorithm.value, BCRYPT_SHA256_ALGORITHM, nullptr, 0));
    HashState hash;
    HashCheck(BCryptCreateHash(algorithm.value, &hash.value, nullptr, 0, nullptr, 0, 0));
    std::array<unsigned char, 65536> buffer{};
    unsigned long long total = 0;
    for (;;) {
        DWORD read = 0;
        Require(ReadFile(file.get(), buffer.data(), static_cast<DWORD>(buffer.size()), &read, nullptr) != FALSE,
            "Hash client marker");
        if (read == 0) break;
        total += read;
        if (total > expected_size) throw std::runtime_error("Client marker changed during hashing.");
        HashCheck(BCryptHashData(hash.value, buffer.data(), read, 0));
    }
    std::array<unsigned char, 32> digest{};
    HashCheck(BCryptFinishHash(hash.value, digest.data(), static_cast<ULONG>(digest.size()), 0));
    std::ostringstream hex;
    for (const auto value : digest) hex << std::hex << std::setfill('0') << std::setw(2) << unsigned(value);
    if (total != expected_size || hex.str() != expected_hash)
        throw std::runtime_error("Client files differ from the verified baseline. Use the pinned client package.");
    return file;
}
void PrepareDesktopPreferences(const std::filesystem::path& path, const Display& display, bool apply) {
    for (auto part = path; !part.empty(); part = part.parent_path()) {
        const DWORD attributes = GetFileAttributesW(part.c_str());
        Require(attributes != INVALID_FILE_ATTRIBUTES, "Read preferences path");
        if (attributes & FILE_ATTRIBUTE_REPARSE_POINT)
            throw std::runtime_error("Preferences must not use path indirection.");
        if (part == part.root_path()) break;
    }
    Handle original(CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_DELETE,
        nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr));
    Require(original.get() != INVALID_HANDLE_VALUE, "Open display preferences");
    LARGE_INTEGER size{};
    Require(GetFileSizeEx(original.get(), &size) != FALSE, "Read preferences size");
    if (size.QuadPart < 0 || size.QuadPart > 1024 * 1024)
        throw std::runtime_error("Client preferences exceed the supported size.");
    std::string before(static_cast<std::size_t>(size.QuadPart), '\0');
    DWORD read = 0;
    Require(ReadFile(original.get(), before.data(), static_cast<DWORD>(before.size()), &read, nullptr) &&
        read == before.size(), "Read display preferences");
    const auto after = DesktopPreferences(before, display);
    if (!apply || after == before) return;
    BY_HANDLE_FILE_INFORMATION initial{};
    Require(GetFileInformationByHandle(original.get(), &initial) != FALSE, "Identify preferences");
    const auto temporary = std::filesystem::path(path.wstring() + L".desktop-" +
        std::to_wstring(GetCurrentProcessId()) + L".tmp");
    bool temporary_owned = false;
    try {
        {
            Handle output(CreateFileW(temporary.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_NEW,
                FILE_ATTRIBUTE_NORMAL, nullptr));
            Require(output.get() != INVALID_HANDLE_VALUE, "Create atomic preferences update");
            temporary_owned = true;
            DWORD written = 0;
            Require(WriteFile(output.get(), after.data(), static_cast<DWORD>(after.size()), &written, nullptr) &&
                written == after.size() && FlushFileBuffers(output.get()), "Write display preferences");
        }
        Handle current(CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_DELETE,
            nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr));
        Require(current.get() != INVALID_HANDLE_VALUE, "Recheck preferences");
        BY_HANDLE_FILE_INFORMATION now{};
        Require(GetFileInformationByHandle(current.get(), &now) != FALSE, "Recheck preferences identity");
        if (initial.dwVolumeSerialNumber != now.dwVolumeSerialNumber || initial.nFileIndexHigh != now.nFileIndexHigh ||
            initial.nFileIndexLow != now.nFileIndexLow || initial.nFileSizeLow != now.nFileSizeLow ||
            initial.nFileSizeHigh != now.nFileSizeHigh || CompareFileTime(&initial.ftLastWriteTime, &now.ftLastWriteTime))
            throw std::runtime_error("Preferences changed during startup; retry after closing their editor.");
        // ReplaceFile retains the original file's ACL and attributes. No backup path is supplied.
        Require(ReplaceFileW(path.c_str(), temporary.c_str(), nullptr, 0, nullptr, nullptr) != FALSE,
            "Commit display preferences");
        temporary_owned = false;
    } catch (...) {
        if (temporary_owned) DeleteFileW(temporary.c_str());
        throw;
    }
}
std::vector<wchar_t> ChildEnvironment() {
    wchar_t* raw = GetEnvironmentStringsW();
    Require(raw != nullptr, "Read environment");
    std::vector<std::wstring> entries;
    std::wstring layer;
    try {
        for (const wchar_t* cursor = raw; *cursor; cursor += wcslen(cursor) + 1) {
            std::wstring value(cursor);
            const auto equals = value.find(L'=', value.front() == L'=' ? 1 : 0);
            if (EqualName(value.substr(0, equals), L"__COMPAT_LAYER")) {
                layer = equals == std::wstring::npos ? L"" : value.substr(equals + 1);
            } else entries.push_back(std::move(value));
        }
    } catch (...) { FreeEnvironmentStringsW(raw); throw; }
    FreeEnvironmentStringsW(raw);
    entries.push_back(L"__COMPAT_LAYER=" + DpiLayer(layer));
    std::sort(entries.begin(), entries.end(), [](const auto& a, const auto& b) {
        return _wcsicmp(a.c_str(), b.c_str()) < 0;
    });
    std::vector<wchar_t> block;
    for (const auto& value : entries) {
        block.insert(block.end(), value.begin(), value.end()); block.push_back(0);
    }
    block.push_back(0);
    return block;
}
std::vector<WindowIdentity> ClientWindows(DWORD process) {
    WindowScan scan{process, {}, false};
    const auto result = EnumWindows(WindowCallback, reinterpret_cast<LPARAM>(&scan));
    Require(result != FALSE && !scan.failed, "Enumerate client windows");
    return scan.items;
}
void ApplyDesktopFrame(const WindowIdentity& identity, HANDLE process, const Display& display) {
    VerifyIdentity(identity, process);
    const auto old = GetWindowLongPtrW(identity.window, GWL_STYLE);
    const auto style = (old & ~(WS_CAPTION | WS_THICKFRAME | WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX)) | WS_POPUP;
    SetStyle(identity.window, GWL_STYLE, style);
    VerifyIdentity(identity, process);
    const auto ex = GetWindowLongPtrW(identity.window, GWL_EXSTYLE);
    SetStyle(identity.window, GWL_EXSTYLE,
        ex & ~(WS_EX_WINDOWEDGE | WS_EX_CLIENTEDGE | WS_EX_DLGMODALFRAME | WS_EX_STATICEDGE));
    VerifyIdentity(identity, process);
    Require(SetWindowPos(identity.window, HWND_NOTOPMOST, display.left, display.top,
        static_cast<int>(display.current.width), static_cast<int>(display.current.height),
        SWP_FRAMECHANGED | SWP_NOACTIVATE | SWP_NOOWNERZORDER) != FALSE, "Place desktop fullscreen window");
}
void VerifyDesktopFrame(const WindowIdentity& identity, HANDLE process, const Display& display) {
    VerifyIdentity(identity, process);
    const auto context = GetWindowDpiAwarenessContext(identity.window);
    if (GetAwarenessFromDpiAwarenessContext(context) == DPI_AWARENESS_UNAWARE)
        throw std::runtime_error("Windows did not apply the client's DPI compatibility setting.");
    RECT area{}; POINT origin{};
    Require(GetClientRect(identity.window, &area) && ClientToScreen(identity.window, &origin),
        "Read client drawing area");
    RECT physical{};
    if (FAILED(DwmGetWindowAttribute(identity.window, DWMWA_EXTENDED_FRAME_BOUNDS,
                                    &physical, sizeof(physical))))
        throw std::runtime_error("Cannot verify the physical fullscreen frame.");
    const auto& mode = display.current;
    if (area.right != static_cast<LONG>(mode.width) || area.bottom != static_cast<LONG>(mode.height) ||
        origin.x != display.left || origin.y != display.top ||
        physical.left != display.left || physical.top != display.top ||
        physical.right - physical.left != static_cast<LONG>(mode.width) ||
        physical.bottom - physical.top != static_cast<LONG>(mode.height) ||
        (GetWindowLongPtrW(identity.window, GWL_STYLE) & (WS_CAPTION | WS_THICKFRAME)) != 0 ||
        (GetWindowLongPtrW(identity.window, GWL_EXSTYLE) & WS_EX_TOPMOST) != 0) {
        throw std::runtime_error("The client drawing area does not match the physical desktop.");
    }
}
std::string Utf8(std::wstring_view text) {
    if (text.empty()) return {};
    const int size = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, text.data(),
        static_cast<int>(text.size()), nullptr, 0, nullptr, nullptr);
    Require(size > 0, "Encode launch report");
    std::string result(static_cast<std::size_t>(size), '\0');
    Require(WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, text.data(), static_cast<int>(text.size()),
        result.data(), size, nullptr, nullptr) == size, "Encode launch report");
    return result;
}
std::string Json(std::string_view text) {
    std::ostringstream result; result << '"';
    for (const unsigned char c : text) {
        if (c == '"' || c == '\\') result << '\\' << c;
        else if (c < 0x20) result << "\\u" << std::hex << std::setw(4) << std::setfill('0') << unsigned(c);
        else result << c;
    }
    return result.str() + '"';
}
std::string Describe(const Display& display) {
    const auto mode = [](const Mode& m) {
        return "{\"width\":" + std::to_string(m.width) + ",\"height\":" + std::to_string(m.height) +
            ",\"refresh\":" + std::to_string(m.refresh) + ",\"bits\":" + std::to_string(m.bits) +
            ",\"orientation\":" + std::to_string(m.orientation) + "}";
    };
    return "{\"device\":" + Json(Utf8(display.device)) + ",\"left\":" + std::to_string(display.left) +
        ",\"top\":" + std::to_string(display.top) + ",\"current\":" + mode(display.current) +
        ",\"desktop\":" + mode(display.desktop) + "}";
}
}  // namespace shadowbane::desktop
