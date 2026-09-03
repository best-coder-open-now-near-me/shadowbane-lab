#pragma once

#include <Windows.h>

#include <cstddef>
#include <cstdint>

namespace wonderbane::extension {

struct SceneFrameState;

struct GraphicsCameraState {
    float position[3U]{};
    float forward[3U]{};
    float up[3U]{};
    float zoom = 0.0F;
    float vertical_fov_degrees = 0.0F;
    float view_matrix[16U]{};
    float projection_matrix[16U]{};
    int viewport[4U]{};
};

bool HasGraphicsExtensionToken(
    const char* extensions,
    const char* token
) noexcept;
bool IsGraphicsVersionAtLeast(
    const char* version,
    unsigned int required_major,
    unsigned int required_minor
) noexcept;

DWORD StartGraphicsStatusPublication() noexcept;
bool GraphicsExecutableSha256Matches(const char* sha256) noexcept;
DWORD ConfigureGraphicsPresentEntry(
    const char* library_name,
    const char* symbol_name,
    std::uint32_t iat_rva,
    const char* runtime_profile
) noexcept;
bool BuildGraphicsCameraState(
    const float* view_matrix,
    std::size_t view_matrix_count,
    const float* projection_matrix,
    std::size_t projection_matrix_count,
    const int* viewport,
    std::size_t viewport_count,
    GraphicsCameraState* state
) noexcept;
bool NeedsGraphicsCameraStateObservation() noexcept;
void ObserveGraphicsCameraState(
    const float* view_matrix,
    std::size_t view_matrix_count,
    const float* projection_matrix,
    std::size_t projection_matrix_count,
    const int* viewport,
    std::size_t viewport_count,
    int model_view_stack_depth
) noexcept;
void ObserveGraphicsPresent() noexcept;
void ReportDepthEdgePassComposite() noexcept;
void ReportDepthEdgePassFailure(const char* reason) noexcept;
void ReportSceneColorCapture() noexcept;
void ReportSceneColorCaptureFailure(const char* reason) noexcept;
void ReportSceneFrameClassification(const SceneFrameState& frame) noexcept;
void StopGraphicsStatusPublication() noexcept;
DWORD GetGraphicsStatusPath(
    wchar_t* destination,
    std::size_t destination_capacity
) noexcept;

}  // namespace wonderbane::extension
