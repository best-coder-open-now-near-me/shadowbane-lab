// Exercise production initialization/rollback with bounded external service seams.
#include <Windows.h>
#include <ShlObj.h>
#include <strsafe.h>
#include <cstring>
DWORD WINAPI FixtureModuleFileName(HMODULE, LPWSTR destination, DWORD capacity) {
    return SUCCEEDED(StringCchCopyW(destination, capacity, L"C:\\fixture\\sb.exe")) ? 17U : 0U;
}
bool fail_heartbeat = false;
HRESULT WINAPI FixtureKnownFolder(REFKNOWNFOLDERID, DWORD, HANDLE, PWSTR* destination) {
    if (fail_heartbeat) { return E_ACCESSDENIED; }
    wchar_t path[MAX_PATH]{};
    const DWORD length = GetTempPathW(MAX_PATH, path);
    if (!length || length >= MAX_PATH) { return E_FAIL; }
    const auto bytes = (static_cast<std::size_t>(length) + 1U) * sizeof(wchar_t);
    *destination = static_cast<PWSTR>(CoTaskMemAlloc(bytes));
    if (!*destination) { return E_OUTOFMEMORY; }
    std::memcpy(*destination, path, bytes); return S_OK;
}
#define GetModuleFileNameW FixtureModuleFileName
#define SHGetKnownFolderPath FixtureKnownFolder
#include "extension.cpp"
#undef GetModuleFileNameW
#undef SHGetKnownFolderPath
#undef NDEBUG
#include <cassert>
namespace wonderbane::extension {
int renderer_starts = 0, renderer_stops = 0, telemetry_starts = 0, telemetry_stops = 0;
int effects_stops = 0, navigation_stops = 0, status_stops = 0, control_stops = 0, event_stops = 0;
DWORD telemetry_result = ERROR_ACCESS_DENIED;
bool IsReviewedWorldMapClient() noexcept { return false; }
DWORD StartWorldMapCapture(HMODULE, const ProcessIdentity&) noexcept { return ERROR_SUCCESS; }
void StopWorldMapCapture() noexcept {}
DWORD InitializeEventChannel(const ProcessIdentity&, std::uint32_t) noexcept { return ERROR_SUCCESS; }
void ShutdownEventChannel() noexcept { ++event_stops; }
DWORD StartGraphicsStatusPublication() noexcept { return ERROR_SUCCESS; }
void StopGraphicsStatusPublication() noexcept { ++status_stops; }
DWORD StartGraphicsControl() noexcept { return ERROR_SUCCESS; }
void StopGraphicsControl() noexcept { ++control_stops; }
DWORD StartNavigationChannel(const ProcessIdentity&) noexcept { return ERROR_SUCCESS; }
void StopNavigationChannel() noexcept { ++navigation_stops; }
DWORD StartEffects(const ProcessIdentity&) noexcept { return ERROR_SUCCESS; }
void StopEffects() noexcept { ++effects_stops; }
DWORD StartStrongCelShading() noexcept { ++renderer_starts; return ERROR_SUCCESS; }
void StopStrongCelShading() noexcept { ++renderer_stops; }
DWORD StartGraphicsPresentObservation() noexcept { return ERROR_SUCCESS; }
void StopGraphicsPresentObservation() noexcept {}
DWORD StartPassiveCameraObservation() noexcept { return ERROR_SUCCESS; }
void StopPassiveCameraObservation() noexcept {}
DWORD SelectPerformanceTelemetryProfile(const wchar_t* value, PerformanceTelemetryProfile* profile) noexcept {
    *profile = wcscmp(value, L"frame") == 0 ? PerformanceTelemetryProfile::frame
                                          : PerformanceTelemetryProfile::disabled;
    return ERROR_SUCCESS;
}
DWORD StartPerformanceTelemetry(const ProcessIdentity&, PerformanceTelemetryProfile) noexcept {
    ++telemetry_starts; return telemetry_result;
}
void StopPerformanceTelemetry() noexcept { ++telemetry_stops; }
}
int main() {
    using namespace wonderbane::extension;
    g_extension_module = GetModuleHandleW(nullptr);
    assert(SetEnvironmentVariableW(kPerformanceProfileEnvironment, L"disabled"));
    assert(WonderBaneExtensionInitialize() == ERROR_SUCCESS);
    assert(renderer_starts == 1 && telemetry_starts == 0 && renderer_stops == 0);
    assert(DeleteFileW(g_heartbeat_path));
    InterlockedExchange(&g_state, static_cast<LONG>(WonderBaneExtensionState::uninitialized));
    assert(SetEnvironmentVariableW(kPerformanceProfileEnvironment, L"frame"));
    assert(WonderBaneExtensionInitialize() == ERROR_SUCCESS);
    assert(renderer_starts == 2 && telemetry_starts == 1 && renderer_stops == 0);
    assert(DeleteFileW(g_heartbeat_path));
    InterlockedExchange(&g_state, static_cast<LONG>(WonderBaneExtensionState::uninitialized));
    telemetry_result = ERROR_SUCCESS; fail_heartbeat = true;
    assert(WonderBaneExtensionInitialize() == ERROR_ACCESS_DENIED);
    assert(renderer_stops == 1 && telemetry_stops == 1 && effects_stops == 1);
    assert(navigation_stops == 1 && status_stops == 1 && control_stops == 1 && event_stops == 1);
    // Failed initialization cannot start a replacement generation implicitly.
    assert(WonderBaneExtensionInitialize() == ERROR_ACCESS_DENIED && renderer_starts == 3);
    return 0;
}
