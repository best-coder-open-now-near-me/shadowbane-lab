#pragma once
#include "policy.h"
#include <Windows.h>
#include <filesystem>
#include <string>
#include <vector>

namespace shadowbane::desktop {
class Handle {
    HANDLE value_ = INVALID_HANDLE_VALUE;
public:
    explicit Handle(HANDLE value = INVALID_HANDLE_VALUE) : value_(value) {}
    ~Handle() { if (value_ && value_ != INVALID_HANDLE_VALUE) CloseHandle(value_); }
    Handle(const Handle&) = delete;
    Handle& operator=(const Handle&) = delete;
    Handle(Handle&& other) noexcept : value_(other.value_) { other.value_ = INVALID_HANDLE_VALUE; }
    HANDLE get() const { return value_; }
};
struct WindowIdentity { HWND window{}; DWORD process{}, thread{}; };
std::vector<Display> Displays();
std::wstring ExecutablePath();
void RequireNoExistingClient(const std::filesystem::path& executable);
Handle VerifyFile(const std::filesystem::path& path, unsigned long long size, const char* hash);
void PrepareDesktopPreferences(const std::filesystem::path& path, const Display& display, bool apply = true);
std::vector<wchar_t> ChildEnvironment();
std::vector<WindowIdentity> ClientWindows(DWORD process);
void ApplyDesktopFrame(const WindowIdentity& identity, HANDLE process, const Display& display);
void VerifyDesktopFrame(const WindowIdentity& identity, HANDLE process, const Display& display);
std::string Utf8(std::wstring_view text);
std::string Json(std::string_view text);
std::string Describe(const Display& display);
}  // namespace shadowbane::desktop
