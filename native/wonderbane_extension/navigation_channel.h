#pragma once
#include "event_channel.h"
#include "navigation_protocol.h"
#include <array>

namespace wonderbane::extension {
struct NavigationFrameBuffer {
    std::array<unsigned char, navigation::kMaximumFrameBytes> bytes{};
    std::uint32_t accepted_sequence = 0U;
    navigation::FrameHeader header{};
};
DWORD StartNavigationChannel(const ProcessIdentity& identity) noexcept;
void StopNavigationChannel() noexcept;
// Caller owns the buffer and serializes its readers. No waits, files, allocation,
// retries or geometry construction occur on this render-thread path.
bool ReadNavigationFrame(NavigationFrameBuffer* buffer) noexcept;
}  // namespace wonderbane::extension
