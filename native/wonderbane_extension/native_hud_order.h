#pragma once
#include <cstdint>
namespace wonderbane::extension {
// The reviewed ArcChannelHud is independent chat UI. It may stay at the head
// of the active HUD list after an ordinary management window opens. Direct
// native transactions must still be blocked by every other intervening HUD,
// including unknown classes, amount quotes and confirmation dialogs.
inline void ObserveActionFront(std::uint32_t& front, std::uintptr_t base,
    std::uint32_t hud, std::uint32_t table) noexcept {
    if (!front && table != base + 0x11659d8) { front = hud; }
}
}
