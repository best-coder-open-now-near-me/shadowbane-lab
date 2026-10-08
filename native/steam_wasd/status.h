#pragma once
#include "image.h"
namespace steam_wasd {
inline constexpr DWORD schema = 1;
inline constexpr wchar_t command_name[] = L"Shadowbane.SteamWASD.Command.v1";
struct Shared {
    volatile LONG sequence{};
    DWORD version{}, pid{}, enabled{}, hooked{}, gate{}, fault{}, keys{}, moving{}, state{};
    ULONGLONG creation{}, tick{}, frames{}, moves{}, stops{}, messages{}, scene_changes{};
    float x{}, y{}, z{}, yaw{};
    char dll_hash[65]{};
};
inline std::wstring mapping_name(DWORD pid) { return L"Local\\Shadowbane.SteamWASD." + std::to_wstring(pid); }
inline ULONGLONG creation_time(HANDLE process) {
    FILETIME c{},e{},k{},u{};
    if (!GetProcessTimes(process,&c,&e,&k,&u)) return 0;
    return (ULONGLONG(c.dwHighDateTime)<<32) | c.dwLowDateTime;
}
}
