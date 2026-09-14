#pragma once

#include <cstddef>
#include <cstdint>

namespace wonderbane::extension::navigation {

constexpr std::uint32_t kMagic = 0x494E4257U;
constexpr std::uint32_t kVersion = 1U;
constexpr std::size_t kMaximumLines = 16384U;
constexpr std::size_t kMaximumCaptureBytes = 1048576U;
constexpr std::uint32_t kEnabled = 1U;
constexpr std::uint32_t kFrozen = 2U;
constexpr std::uint32_t kXray = 4U;
constexpr std::uint32_t kUnknownHeight = 8U;
constexpr std::uint32_t kWorldHeight = 1U;
constexpr std::uint32_t kOverlap = 2U;
constexpr std::uint32_t kTrailLayer = 128U;
constexpr std::uint32_t kAllLayers = 511U;

#pragma pack(push, 4)
struct FrameHeader {
    std::uint32_t magic;
    std::uint32_t version;
    std::uint32_t size;
    std::uint32_t sequence;
    std::uint32_t process_id;
    std::uint32_t flags;
    std::uint64_t process_creation;
    std::uint64_t session_id;
    std::uint64_t zone_id;
    std::uint64_t map_revision;
    std::uint64_t route_revision;
    std::uint64_t sampled_ms;
    std::uint64_t lease_ms;
    std::uint64_t live_zone_id;
    std::uint32_t line_count;
    std::uint32_t omitted_lines;
    std::uint32_t capture_size;
    std::uint32_t checksum;
    std::uint32_t layer_mask;
    std::uint32_t status;
    float center_lt;
    float center_lg;
    float view_radius;
    float reserved;
};
struct ControlFrame {
    std::uint32_t magic, version, size, sequence;
    std::uint64_t process_creation, session_id;
    std::uint32_t process_id, flags, layer_mask, command;
    float character_radius, movement_uncertainty, margin;
    std::uint32_t checksum;
};
struct Line {
    std::uint32_t layer;
    std::uint32_t flags;
    float start[3];
    float end[3];
};
#pragma pack(pop)
static_assert(sizeof(FrameHeader) == 128U);
static_assert(offsetof(FrameHeader, sequence) == 12U);
static_assert(offsetof(FrameHeader, checksum) == 100U);
static_assert(sizeof(Line) == 32U);
static_assert(sizeof(ControlFrame) == 64U);
static_assert(offsetof(ControlFrame, checksum) == 60U);
constexpr std::size_t kMaximumFrameBytes = sizeof(FrameHeader)
    + kMaximumLines * sizeof(Line) + kMaximumCaptureBytes;
// Reserved versioned panel control area; each writer owns its own sequence.
constexpr std::size_t kControlBytes = 64U;
constexpr std::size_t kMappingBytes = kMaximumFrameBytes + kControlBytes;

enum class FrameError {
    none, size, header, sequence, identity, zone, flags, capacity, coordinates,
    lease, stale, checksum, line
};
std::uint32_t FrameChecksum(const void* data, std::size_t size) noexcept;
FrameError ValidateFrame(const void* data, std::size_t size,
                         std::uint32_t sequence_after, std::uint32_t process_id,
                         std::uint64_t process_creation, std::uint64_t now_ms) noexcept;
bool FrameLeaseValid(const FrameHeader& frame, std::uint64_t now_ms) noexcept;
bool FramePlacementValid(const FrameHeader& frame, std::uint64_t now_ms) noexcept;
// Historical evidence still requires complete geometry, CRC and exact identity.
// This does not authorize world placement or renew a producer/zone lease.
FrameError ValidateEvidenceFrame(const void* data, std::size_t size,
    std::uint32_t sequence_after, std::uint32_t process_id,
    std::uint64_t process_creation, std::uint64_t now_ms) noexcept;
bool ValidateControls(const ControlFrame& controls, std::uint32_t sequence_after,
    const FrameHeader& frame) noexcept;

}  // namespace wonderbane::extension::navigation
