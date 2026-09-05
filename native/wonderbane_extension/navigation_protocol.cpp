#include "navigation_protocol.h"

#include <array>
#include <cmath>
#include <cstring>

namespace wonderbane::extension::navigation {
namespace {
constexpr auto MakeCrcTable() noexcept {
    std::array<std::uint32_t, 256U> table{};
    for (std::uint32_t i = 0; i < 256U; ++i) {
        auto value = i;
        for (unsigned bit = 0; bit < 8U; ++bit) {
            value = (value >> 1U) ^ ((value & 1U) ? 0xEDB88320U : 0U);
        }
        table[i] = value;
    }
    return table;
}
constexpr auto kCrcTable = MakeCrcTable();
bool Coordinate(const float value) noexcept {
    return std::isfinite(value) && std::fabs(value) <= 1.0e9F;
}
}  // namespace

std::uint32_t FrameChecksum(const void* const data, const std::size_t size) noexcept {
    if (data == nullptr) {
        return 0U;
    }
    const auto* bytes = static_cast<const unsigned char*>(data);
    std::uint32_t crc = 0xFFFFFFFFU;
    for (std::size_t i = 0; i < size; ++i) {
        // Checksum includes the entire header and payload with its own slot zero.
        const auto value = (i >= 100U && i < 104U) ? 0U : bytes[i];
        crc = kCrcTable[(crc ^ value) & 0xFFU] ^ (crc >> 8U);
    }
    return crc ^ 0xFFFFFFFFU;
}

bool FrameLeaseValid(const FrameHeader& frame, const std::uint64_t now_ms) noexcept {
    return frame.lease_ms <= now_ms && now_ms - frame.lease_ms <= 2000U
        && frame.sampled_ms <= frame.lease_ms
        && ((frame.flags & kFrozen) != 0U || now_ms - frame.sampled_ms <= 2000U);
}

FrameError ValidateEvidenceFrame(const void* const data, const std::size_t size,
                         const std::uint32_t sequence_after, const std::uint32_t process_id,
                         const std::uint64_t process_creation, const std::uint64_t now_ms) noexcept {
    if (data == nullptr || size < sizeof(FrameHeader) || size > kMaximumFrameBytes) {
        return FrameError::size;
    }
    FrameHeader frame{};
    std::memcpy(&frame, data, sizeof(frame));
    if (frame.magic != kMagic || frame.version != kVersion || frame.size != size) {
        return FrameError::header;
    }
    if (frame.sequence == 0U || (frame.sequence & 1U) != 0U || frame.sequence != sequence_after) {
        return FrameError::sequence;
    }
    if (frame.process_id == 0U || frame.process_creation == 0U || frame.session_id == 0U
        || frame.process_id != process_id || frame.process_creation != process_creation) {
        return FrameError::identity;
    }
    if ((frame.flags & ~15U) != 0U || (frame.layer_mask & ~kAllLayers) != 0U
        || (frame.status & ~1U) != 0U || frame.reserved != 0.0F) {
        return FrameError::flags;
    }
    if (frame.line_count > kMaximumLines || frame.capture_size > kMaximumCaptureBytes
        || size != sizeof(FrameHeader) + frame.line_count * sizeof(Line) + frame.capture_size) {
        return FrameError::capacity;
    }
    if (!Coordinate(frame.center_lt) || !Coordinate(frame.center_lg)
        || !Coordinate(frame.view_radius) || frame.view_radius <= 0.0F) {
        return FrameError::coordinates;
    }
    if (frame.lease_ms > now_ms || frame.sampled_ms > frame.lease_ms) {
        return FrameError::lease;
    }
    if (frame.checksum != FrameChecksum(data, size)) {
        return FrameError::checksum;
    }
    const auto* lines = static_cast<const unsigned char*>(data) + sizeof(FrameHeader);
    for (std::uint32_t i = 0U; i < frame.line_count; ++i) {
        Line line{};
        std::memcpy(&line, lines + i * sizeof(Line), sizeof(Line));
        if (line.layer == 0U || (line.layer & (line.layer - 1U)) != 0U
            || (line.layer & ~kAllLayers) != 0U || (line.flags & ~3U) != 0U
            || ((line.flags & kWorldHeight) != 0U && line.layer != kTrailLayer)) {
            return FrameError::line;
        }
        for (unsigned axis = 0; axis < 3U; ++axis) {
            if (!Coordinate(line.start[axis]) || !Coordinate(line.end[axis])) {
                return FrameError::coordinates;
            }
        }
    }
    return FrameError::none;
}
bool FramePlacementValid(const FrameHeader& frame, const std::uint64_t now_ms) noexcept {
    return frame.zone_id != 0U && frame.zone_id == frame.live_zone_id
        && FrameLeaseValid(frame, now_ms);
}

FrameError ValidateFrame(const void* const data, const std::size_t size,
    const std::uint32_t sequence_after, const std::uint32_t process_id,
    const std::uint64_t process_creation, const std::uint64_t now_ms) noexcept {
    const auto error = ValidateEvidenceFrame(data, size, sequence_after,
        process_id, process_creation, now_ms);
    if (error != FrameError::none) return error;
    FrameHeader frame{};
    std::memcpy(&frame, data, sizeof(frame));
    if (frame.zone_id == 0U || frame.zone_id != frame.live_zone_id) return FrameError::zone;
    if (now_ms - frame.lease_ms > 2000U) return FrameError::lease;
    return FrameLeaseValid(frame, now_ms) ? FrameError::none : FrameError::stale;
}

bool ValidateControls(const ControlFrame& controls, const std::uint32_t sequence_after,
                      const FrameHeader& frame) noexcept {
    if (controls.magic != 0x434E4257U || controls.version != kVersion
        || controls.size != sizeof(controls) || controls.sequence == 0U
        || (controls.sequence & 1U) != 0U || controls.sequence != sequence_after
        || controls.process_id != frame.process_id
        || controls.process_creation != frame.process_creation
        || (controls.session_id != 0U && controls.session_id != frame.session_id)
        || (controls.flags & ~7U) != 0U || (controls.layer_mask & ~kAllLayers) != 0U
        || controls.command > 2U) return false;
    for (const float value : {controls.character_radius, controls.movement_uncertainty,
                              controls.margin}) {
        if (!Coordinate(value) || value < 0.0F) return false;
    }
    auto checked = controls;
    checked.checksum = 0U;
    return controls.checksum == FrameChecksum(&checked, sizeof(checked));
}
}  // namespace wonderbane::extension::navigation
