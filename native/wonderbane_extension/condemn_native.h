#pragma once
#include "movement_lifetime.h"
#include <array>
#include <cstdint>
namespace wonderbane::extension::condemn::native {
using Key = std::array<std::uint32_t, 2>;
struct Target {
    Key building{}, identity{};
    std::uint32_t scope = 0; // 4=guild, 5=nation. Never merge equal keys across scopes.
    bool operator==(const Target&) const = default;
};
struct Snapshot {
    std::uint64_t scene = 0;
    Key local{};
    std::uint32_t root = 0, manager = 0, building_hud = 0, front = 0, open_button = 0;
    Key building{};
    std::uint32_t kos = 0, list = 0, selected = 0, list_selected = 0, count = 0;
    Key context{};
    std::array<Key, 3> pending{};
    std::uint32_t flags = 0, row = 0, entry = 0, enabled = 0, collision = 0;
    Key entry_key{};
    bool operator==(const Snapshot&) const = default;
};
enum class Action { open, add, enable };
enum class Result { unavailable, submitted, uncertain };
using Admission = bool (*)(void*) noexcept;
bool Valid(const Target&) noexcept;
// No native call or scene rearming. Read complete ownership, not just a matching label.
bool Capture(std::uintptr_t, const movement::NativeScene&, const Target&, Snapshot&) noexcept;
// Caller owns the verified image and native owner thread. Admission must renew
// producer/deadline/foreground and shared UI ownership immediately before every
// side effect. A submitted result means call-through only, never server acceptance.
// The transaction owner journals before entry and never retries an uncertain call.
Result Invoke(std::uintptr_t, const movement::NativeScene&, const Target&, Action,
    const Snapshot&, Admission, void*) noexcept;
}
