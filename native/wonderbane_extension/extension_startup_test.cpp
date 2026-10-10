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
DWORD telemetry_result = ERROR_ACCESS_DENIED, trace_result = ERROR_SUCCESS;
int trace_stops = 0, targeted_starts = 0, targeted_stops = 0;
DWORD targeted_result = ERROR_SUCCESS;
DWORD graphics_result = ERROR_SUCCESS;
bool graphics_identity_ready = false;
int graphics_starts = 0;
namespace actor_effects {
int starts = 0;
bool StartAtBootstrap(std::uintptr_t image,std::uintptr_t initializer_return) noexcept {
    assert(image==reinterpret_cast<std::uintptr_t>(GetModuleHandleW(nullptr)));
    assert(initializer_return && starts==targeted_starts);
    // Model the actual graphics-owned SHA cache: it is empty at cold startup.
    // The public observer requires that identity before it can install hooks.
    assert(graphics_identity_ready && graphics_result == ERROR_SUCCESS);
    ++starts;
    return false; // Unsupported early observation cannot prevent ordinary startup.
}
}
DWORD StartTargetedActionTrace(const ProcessIdentity& identity) noexcept {
    assert(identity.process_id == GetCurrentProcessId() && identity.creation_filetime_utc);
    ++targeted_starts; return targeted_result;
}
void StopTargetedActionTrace() noexcept { ++targeted_stops; }
namespace condemn {
int starts = 0, stops = 0;
DWORD result = ERROR_SUCCESS;
DWORD Start(const ProcessIdentity& identity) noexcept {
    assert(identity.process_id == GetCurrentProcessId() && identity.creation_filetime_utc);
    ++starts; return result;
}
void Stop() noexcept { ++stops; }
}
namespace tracking {
int starts = 0, stops = 0;
DWORD result = ERROR_SUCCESS;
bool readable = false;
ProcessIdentity bound{};
DWORD Start(const ProcessIdentity& identity) noexcept {
    assert(identity.process_id == GetCurrentProcessId() && identity.creation_filetime_utc);
    assert(graphics_identity_ready);
    ++starts; bound = identity; readable = result == ERROR_SUCCESS; return result;
}
void Stop() noexcept { ++stops; readable = false; }
bool ReadCursor(Cursor& cursor) noexcept {
    cursor = {};
    if (!readable) { return false; }
    cursor.process_id = bound.process_id; cursor.creation = bound.creation_filetime_utc;
    return true;
}
}
namespace group_messages {
int starts=0,stops=0;
DWORD result=ERROR_SUCCESS;
DWORD Start(const ProcessIdentity& identity) noexcept {
    assert(identity.process_id==GetCurrentProcessId()&&identity.creation_filetime_utc&&graphics_identity_ready);
    ++starts;return result;
}
void Stop() noexcept {++stops;}
}
namespace group_updates {
int starts=0,stops=0;
DWORD result=ERROR_SUCCESS;
DWORD Start(const ProcessIdentity& identity) noexcept {
    assert(identity.process_id==GetCurrentProcessId()&&identity.creation_filetime_utc&&graphics_identity_ready);
    ++starts;return result;
}
void Stop() noexcept {++stops;}
}
namespace vendor { bool Start() noexcept { return true; } }
namespace combat {
int starts = 0;
bool Start(const ProcessIdentity& identity) noexcept {
    assert(identity.process_id == GetCurrentProcessId() && identity.creation_filetime_utc);
    assert(g_heartbeat_path[0] && !fail_heartbeat); ++starts;
    return false; // Unsupported combat must not prevent ordinary client startup.
}
}
namespace movement {
int starts = 0;
DWORD start_result = ERROR_SUCCESS;
DWORD StartNativeMovementControls(const ProcessIdentity& identity) noexcept {
    ++starts;
    assert(identity.process_id == GetCurrentProcessId() && identity.creation_filetime_utc);
    // Production startup must publish its successful heartbeat before the optional
    // consumer can install anything. Rollback never registers this dependency.
    assert(g_heartbeat_path[0] && GetFileAttributesW(g_heartbeat_path) != INVALID_FILE_ATTRIBUTES);
    assert(!fail_heartbeat);
    return start_result;
}
}
DWORD StartMovementBoundaryTrace(const ProcessIdentity&) noexcept { return trace_result; }
void StopMovementBoundaryTrace() noexcept { ++trace_stops; }
bool IsReviewedWorldMapClient() noexcept { return false; }
DWORD StartWorldMapCapture(HMODULE, const ProcessIdentity&) noexcept { return ERROR_SUCCESS; }
void StopWorldMapCapture() noexcept {}
DWORD InitializeEventChannel(const ProcessIdentity&, std::uint32_t) noexcept { return ERROR_SUCCESS; }
void ShutdownEventChannel() noexcept { ++event_stops; }
DWORD StartGraphicsStatusPublication() noexcept {
    ++graphics_starts;
    graphics_identity_ready = graphics_result == ERROR_SUCCESS;
    return graphics_result;
}
void StopGraphicsStatusPublication() noexcept { ++status_stops; graphics_identity_ready = false; }
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
namespace wonderbane::extension::item_trace {extern unsigned starts,stops;}
int main() {
    using namespace wonderbane::extension;
    g_extension_module = GetModuleHandleW(nullptr);
    assert(SetEnvironmentVariableW(kPerformanceProfileEnvironment, L"disabled"));
    assert(!graphics_identity_ready && graphics_starts == 0);
    assert(!NativeTrackingResponsesReady());
    assert(WonderBaneExtensionInitialize() == ERROR_SUCCESS);
    assert(graphics_identity_ready && graphics_starts == 1);
    assert(renderer_starts == 1 && telemetry_starts == 0 && renderer_stops == 0);
    assert(movement::starts == 1 && targeted_starts == 1 && targeted_stops == 0);
    assert(condemn::starts == 1 && condemn::stops == 0);
    assert(tracking::starts == 1 && tracking::stops == 0 && NativeTrackingResponsesReady());
    tracking::readable = false;
    assert(!NativeTrackingResponsesReady()); // Capability reads live publication availability.
    tracking::readable = true;
    assert(item_trace::starts==1 && item_trace::stops==0);
    assert(group_messages::starts==1 && group_updates::starts==1);
    assert(combat::starts == 1 && actor_effects::starts == 1);
    assert(WonderBaneExtensionInitialize() == ERROR_SUCCESS && movement::starts == 1);
    assert(actor_effects::starts == 1 && graphics_starts == 1);
    assert(tracking::starts == 1 && NativeTrackingResponsesReady());
    assert(DeleteFileW(g_heartbeat_path));
    InterlockedExchange(&g_state, static_cast<LONG>(WonderBaneExtensionState::uninitialized));
    targeted_result = ERROR_NOT_SUPPORTED; condemn::result = ERROR_NOT_SUPPORTED;
    tracking::result = ERROR_NOT_SUPPORTED;
    group_messages::result=group_updates::result=ERROR_NOT_SUPPORTED;
    trace_result = ERROR_ACCESS_DENIED; movement::start_result = ERROR_NOT_SUPPORTED;
    assert(SetEnvironmentVariableW(kPerformanceProfileEnvironment, L"frame"));
    assert(WonderBaneExtensionInitialize() == ERROR_SUCCESS);
    assert(renderer_starts == 2 && telemetry_starts == 1 && renderer_stops == 0 && trace_stops == 1);
    assert(targeted_starts == 2 && targeted_stops == 0);
    assert(condemn::starts == 2 && condemn::stops == 0);
    assert(tracking::starts == 2 && tracking::stops == 0 && !NativeTrackingResponsesReady());
    assert(movement::starts == 2); // Unsupported optional controls preserve client startup.
    assert(group_messages::starts==2 && group_updates::starts==2);
    assert(DeleteFileW(g_heartbeat_path));
    InterlockedExchange(&g_state, static_cast<LONG>(WonderBaneExtensionState::uninitialized));
    targeted_result = ERROR_SUCCESS; condemn::result = ERROR_SUCCESS;
    tracking::result = ERROR_SUCCESS;
    group_messages::result=group_updates::result=ERROR_SUCCESS;
    telemetry_result = ERROR_SUCCESS; trace_result = ERROR_SUCCESS; fail_heartbeat = true;
    assert(WonderBaneExtensionInitialize() == ERROR_ACCESS_DENIED);
    assert(targeted_starts == 3 && targeted_stops == 1);
    assert(condemn::starts == 3 && condemn::stops == 1);
    assert(tracking::starts == 3 && tracking::stops == 1 && !NativeTrackingResponsesReady());
    assert(item_trace::starts==3 && item_trace::stops==1);
    assert(group_messages::starts==3 && group_updates::starts==3 && group_messages::stops==1 && group_updates::stops==1);
    assert(renderer_stops == 1 && telemetry_stops == 1 && effects_stops == 1 && trace_stops == 2);
    assert(movement::starts == 2); // Failed shared startup did not register a consumer.
    assert(combat::starts == 2 && actor_effects::starts == 3);
    assert(navigation_stops == 1 && status_stops == 1 && control_stops == 1 && event_stops == 1);
    // Failed initialization cannot start a replacement generation implicitly.
    assert(WonderBaneExtensionInitialize() == ERROR_ACCESS_DENIED && renderer_starts == 3);
    assert(targeted_starts == 3 && targeted_stops == 1);
    assert(condemn::starts == 3 && condemn::stops == 1);
    assert(tracking::starts == 3 && tracking::stops == 1 && !NativeTrackingResponsesReady());
    assert(item_trace::starts==3 && item_trace::stops==1);
    // A fresh process whose identity publication fails must never attempt the
    // pre-entry observer; retrying the failed initializer remains inert.
    InterlockedExchange(&g_state, static_cast<LONG>(WonderBaneExtensionState::uninitialized));
    assert(!graphics_identity_ready); // Prior failed initialization shut status down.
    fail_heartbeat = false; graphics_result = ERROR_ACCESS_DENIED;
    const int before_observer = actor_effects::starts;
    const int before_graphics = graphics_starts;
    const int before_targeted = targeted_starts;
    const int before_tracking = tracking::starts;
    const int before_group = group_messages::starts;
    assert(WonderBaneExtensionInitialize() == ERROR_ACCESS_DENIED);
    assert(graphics_starts == before_graphics + 1 && !graphics_identity_ready);
    assert(actor_effects::starts == before_observer && targeted_starts == before_targeted);
    assert(tracking::starts == before_tracking && !NativeTrackingResponsesReady());
    assert(group_messages::starts==before_group && group_updates::starts==before_group);
    assert(WonderBaneExtensionInitialize() == ERROR_ACCESS_DENIED);
    assert(graphics_starts == before_graphics + 1 && actor_effects::starts == before_observer);
    return 0;
}

namespace wonderbane::extension::item_trace {
unsigned starts{},stops{};
DWORD Start(const ProcessIdentity&) noexcept {++starts;return ERROR_NOT_SUPPORTED;}
void Stop() noexcept {++stops;}
}
