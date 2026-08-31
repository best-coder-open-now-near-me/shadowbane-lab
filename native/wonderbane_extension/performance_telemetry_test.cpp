#include "performance_telemetry.h"

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

int main() {
    using wonderbane::extension::CacheArchiveKind;
    using wonderbane::extension::ClassifyCacheArchivePath;
    using wonderbane::extension::EstimateTextureUploadBytes;
    using wonderbane::extension::FormatPerformanceTelemetryMappingName;
    using wonderbane::extension::ProcessIdentity;

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
    return 0;
}
