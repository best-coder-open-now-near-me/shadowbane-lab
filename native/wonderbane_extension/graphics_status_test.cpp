#include "graphics_status.h"
#include "graphics_control.h"

#include <Windows.h>

#include <array>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <string>

namespace {

int Fail(const wchar_t* const operation) noexcept {
    ::fwprintf(stderr, L"%s failed\n", operation);
    return 1;
}

}  // namespace

int wmain() {
    using wonderbane::extension::ConfigureGraphicsPresentEntry;
    using wonderbane::extension::GetGraphicsStatusPath;
    using wonderbane::extension::HasGraphicsExtensionToken;
    using wonderbane::extension::IsGraphicsVersionAtLeast;
    using wonderbane::extension::ObserveGraphicsPresent;
    using wonderbane::extension::ReportDepthEdgePassComposite;
    using wonderbane::extension::StartGraphicsControl;
    using wonderbane::extension::StartGraphicsStatusPublication;
    using wonderbane::extension::StopGraphicsControl;
    using wonderbane::extension::StopGraphicsStatusPublication;

    constexpr char extensions[] =
        "GL_ARB_depth_texture GL_EXT_framebuffer_object GL_EXT_texture3D";
    if (!HasGraphicsExtensionToken(extensions, "GL_ARB_depth_texture")
        || !HasGraphicsExtensionToken(extensions, "GL_EXT_framebuffer_object")
        || HasGraphicsExtensionToken(extensions, "GL_EXT_framebuffer")
        || HasGraphicsExtensionToken(extensions, "")) {
        return Fail(L"extension token matching");
    }
    if (!IsGraphicsVersionAtLeast("2.1.0 fixture", 1U, 4U)
        || !IsGraphicsVersionAtLeast("1.4 fixture", 1U, 4U)
        || IsGraphicsVersionAtLeast("1.3 fixture", 1U, 4U)
        || IsGraphicsVersionAtLeast("vendor", 1U, 0U)) {
        return Fail(L"graphics version parsing");
    }
    DWORD result = StartGraphicsStatusPublication();
    if (result != ERROR_SUCCESS) {
        return Fail(L"status publisher startup");
    }
    result = StartGraphicsControl();
    if (result != ERROR_SUCCESS) {
        StopGraphicsStatusPublication();
        return Fail(L"graphics control startup");
    }
    result = ConfigureGraphicsPresentEntry(
        "GDI32.dll",
        "SwapBuffers",
        23'789'964U,
        "diagnostics-only"
    );
    if (result != ERROR_SUCCESS) {
        StopGraphicsControl();
        StopGraphicsStatusPublication();
        return Fail(L"present entry configuration");
    }
    ObserveGraphicsPresent();
    ReportDepthEdgePassComposite();
    std::array<wchar_t, 1024U> path{};
    result = GetGraphicsStatusPath(path.data(), path.size());
    if (result != ERROR_SUCCESS || path[0] == L'\0') {
        StopGraphicsControl();
        StopGraphicsStatusPublication();
        return Fail(L"status path");
    }
    bool observed = false;
    std::string json{};
    for (DWORD poll = 0U; poll < 100U; ++poll) {
        std::ifstream stream(std::filesystem::path(path.data()), std::ios::binary);
        if (stream) {
            json.assign(
                std::istreambuf_iterator<char>(stream),
                std::istreambuf_iterator<char>()
            );
            stream.close();
            if (json.find("\"call_count\":1") != std::string::npos
                && json.find("\"state\":\"active\"") != std::string::npos) {
                observed = true;
                break;
            }
        }
        Sleep(20U);
    }
    Sleep(2U);
    ObserveGraphicsPresent();
    Sleep(2U);
    ObserveGraphicsPresent();
    StopGraphicsStatusPublication();
    StopGraphicsControl();
    {
        std::ifstream stream(std::filesystem::path(path.data()), std::ios::binary);
        if (stream) {
            json.assign(
                std::istreambuf_iterator<char>(stream),
                std::istreambuf_iterator<char>()
            );
        }
    }
    DeleteFileW(path.data());
    if (!observed
        || json.find("\"producer_id\":\"wonderbane-extension.graphics\"")
            == std::string::npos
        || json.find("\"schema_version\":2") == std::string::npos
        || json.find("\"runtime_profile\":\"diagnostics-only\"")
            == std::string::npos
        || json.find("\"call_count\":3") == std::string::npos
        || json.find("\"clock\":\"windows-query-performance-counter\"")
            == std::string::npos
        || json.find("\"sample_count\":3") == std::string::npos
        || json.find("\"samples\":[[1,") == std::string::npos
        || json.find("\"iat_rva\":23789964") == std::string::npos
        || json.find("\"executable_sha256\":\"") == std::string::npos
        || json.find("\"context_observed\":false") == std::string::npos
        || json.find("\"composite_count\":1") == std::string::npos
        || json.find("\"radius_pixels\":1.0") == std::string::npos
        || json.find("\"edge_metric\":\"single-owner-inverse-depth-curvature\"")
            == std::string::npos
        || json.find("\"sample_kernel\":\"cardinal-five-sample\"")
            == std::string::npos
        || json.find("\"live_controls\":{\"available\":true")
            == std::string::npos
        || json.find("\"mapping_name\":\"Local\\\\WonderBaneGraphicsControl-")
            == std::string::npos
        || json.find("\"desired_sequence\":2,\"applied_sequence\":2")
            == std::string::npos) {
        ::fprintf(stderr, "status JSON: %s\n", json.c_str());
        return Fail(L"published status JSON");
    }
    return 0;
}
