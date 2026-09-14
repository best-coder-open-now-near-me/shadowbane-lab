#include "performance_telemetry.cpp"
#include <thread>

#include <Windows.h>

#include <cstdint>
#include <iostream>
#include <string>

namespace {

int Fail(const char* const detail) {
    std::cerr << detail << '\n';
    return 1;
}

}  // namespace

HANDLE callback_entered = nullptr;
HANDLE callback_release = nullptr;
BOOL WINAPI HeldRead(HANDLE, LPVOID, DWORD, LPDWORD bytes, LPOVERLAPPED) {
    SetEvent(callback_entered);
    WaitForSingleObject(callback_release, INFINITE);
    *bytes = 1;
    return TRUE;
}

int LifetimeRegression() {
    using namespace wonderbane::extension;
    callback_entered = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    callback_release = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    if (StartPerformanceTelemetry({GetCurrentProcessId(), 12345}, PerformanceTelemetryProfile::frame)
        != ERROR_SUCCESS) { return Fail("lifetime mapping start"); }
    InterlockedExchangePointer(&g_original_read_file, reinterpret_cast<PVOID>(&HeldRead));
    const HANDLE tracked = reinterpret_cast<HANDLE>(123);
    TrackHandle(tracked, CacheArchiveKind::textures);
    std::thread callback([&] { DWORD bytes = 0; TelemetryReadFile(tracked, nullptr, 1, &bytes, nullptr); });
    WaitForSingleObject(callback_entered, INFINITE);
    // The original call is deliberately blocked: the production entry lease
    // must still own storage, including while cleanup waits to acquire it.
    if (TryAcquireSRWLockExclusive(&g_lifetime_lock)) { std::abort(); }
    HANDLE stop_entered = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    std::thread cleanup([&] { SetEvent(stop_entered); StopPerformanceTelemetry(); });
    WaitForSingleObject(stop_entered, INFINITE);
    SetEvent(callback_release);
    callback.join(); cleanup.join();
    if (g_storage != nullptr || LoadFunction<PVOID>(&g_original_read_file) == nullptr) {
        return Fail("cleanup storage/call-through lifetime");
    }
    DWORD bytes = 0;
    if (!TelemetryReadFile(tracked, nullptr, 1, &bytes, nullptr) || bytes != 1) {
        return Fail("already dispatched callback after restore");
    }
    StopPerformanceTelemetry();
    if (StartPerformanceTelemetry({GetCurrentProcessId(), 12345}, PerformanceTelemetryProfile::frame)
        != ERROR_SUCCESS) { return Fail("replacement generation"); }
    ObservePerformancePresent(1, true);
    if (g_storage->header.frame_count != 0) { return Fail("previous present entered replacement"); }
    StopPerformanceTelemetry();
    CloseHandle(stop_entered); CloseHandle(callback_entered); CloseHandle(callback_release);
    return 0;
}

int main() {
    if (LifetimeRegression() != 0) { return 1; }
    using wonderbane::extension::CacheArchiveKind;
    using wonderbane::extension::ClassifyCacheArchivePath;
    using wonderbane::extension::EstimateTextureUploadBytes;
    using wonderbane::extension::FormatPerformanceTelemetryMappingName;
    using wonderbane::extension::PerformanceTelemetryProfile;
    using wonderbane::extension::ProcessIdentity;
    using wonderbane::extension::SelectPerformanceTelemetryProfile;

    wchar_t mapping_name[160]{};
    if (
        FormatPerformanceTelemetryMappingName(
            ProcessIdentity{42U, 1000U},
            mapping_name,
            160U
        ) != ERROR_SUCCESS
        || std::wstring(mapping_name)
            != L"Local\\ShadowbaneLab.Extension.Performance.42.1000"
    ) {
        return Fail("performance mapping name did not bind the exact process lifetime");
    }
    if (
        ClassifyCacheArchivePath("C:\\game\\cache\\Textures.cache")
            != CacheArchiveKind::textures
        || ClassifyCacheArchivePath(L"c:/game/CACHE/terrainalpha.CACHE")
            != CacheArchiveKind::terrain_alpha
        || ClassifyCacheArchivePath("C:\\game\\cache\\custom.cache")
            != CacheArchiveKind::other
        || ClassifyCacheArchivePath("C:\\game\\sb.exe")
            != CacheArchiveKind::none
    ) {
        return Fail("cache archive classification is not bounded to cache files");
    }
    if (
        EstimateTextureUploadBytes(2048, 2048, 0x1908U, 0x1401U)
            != 16U * 1024U * 1024U
        || EstimateTextureUploadBytes(1024, 512, 0x1907U, 0x1401U)
            != 3U * 1024U * 512U
        || EstimateTextureUploadBytes(-1, 512, 0x1908U, 0x1401U) != 0U
    ) {
        return Fail("texture upload byte estimates are incorrect");
    }
    PerformanceTelemetryProfile profile{};
    if (
        SelectPerformanceTelemetryProfile(nullptr, &profile) != ERROR_SUCCESS
        || profile != PerformanceTelemetryProfile::frame
        || SelectPerformanceTelemetryProfile(L"frame", &profile) != ERROR_SUCCESS
        || profile != PerformanceTelemetryProfile::frame
        || SelectPerformanceTelemetryProfile(L"off", &profile) != ERROR_SUCCESS
        || profile != PerformanceTelemetryProfile::disabled
        || SelectPerformanceTelemetryProfile(L"full", &profile) != ERROR_SUCCESS
        || profile != PerformanceTelemetryProfile::full
        || SelectPerformanceTelemetryProfile(L"aggregate", &profile) != ERROR_SUCCESS
        || profile != PerformanceTelemetryProfile::aggregate
        || SelectPerformanceTelemetryProfile(L"FULL", &profile) != ERROR_INVALID_DATA
        || SelectPerformanceTelemetryProfile(L"frame", nullptr) != ERROR_INVALID_PARAMETER
    ) {
        return Fail("performance profile policy is incorrect");
    }
    return 0;
}
