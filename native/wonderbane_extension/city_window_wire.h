#pragma once
#include "vendor_wire.h"
namespace wonderbane::extension::city_window::wire {
using Outcome = vendor::wire::Outcome;
enum class Verb : std::uint32_t { inspect = 11, open = 12 };
constexpr std::uint32_t magic = 0x57424331, ready = 1;
#pragma pack(push, 1)
struct Snapshot {
    std::uint64_t scene = 0, revision = 0;
    std::uint32_t root = 0, manager = 0, hud = 0, active_manager = 0;
    std::uint32_t mode = 0, loading = 0, building_count = 0, visible = 0;
    std::uint8_t reserved[16]{};
};
struct Command {
    movement::wire::Host host{};
    std::uint64_t window = 0;
    std::array<std::uint8_t, 16> request{};
    Snapshot expected{};
    std::uint8_t reserved[472]{};
};
struct Receipt {
    std::array<std::uint8_t, 16> request{};
    movement::wire::Host host{};
    std::uint64_t window = 0;
    std::uint32_t outcome = 0, flags = 0;
    Snapshot snapshot{};
    std::uint32_t signature = magic;
    std::uint8_t reserved[268]{};
};
#pragma pack(pop)
static_assert(sizeof(Snapshot) == 64 && sizeof(Command) == 576 && sizeof(Receipt) == 384);
inline bool Equal(const Snapshot& a, const Snapshot& b) noexcept {
    return std::memcmp(&a, &b, sizeof(a)) == 0;
}
inline bool ValidSnapshot(const Snapshot& s) noexcept {
    return s.scene && s.revision && s.root && s.manager && s.mode <= 2
        && s.loading <= 1 && s.visible <= 1 && s.building_count <= 512
        && (!s.visible || (s.hud && s.mode))
        && (s.hud || (!s.visible && !s.loading))
        && movement::wire::Zero(s.reserved, sizeof(s.reserved));
}
inline bool Valid(Verb v, const Command& c) noexcept {
    if (!movement::wire::Valid(c.host) || !c.window || c.window > UINT32_MAX
        || movement::wire::Zero(c.request.data(), c.request.size())
        || !movement::wire::Zero(c.reserved, sizeof(c.reserved))) { return false; }
    return (v == Verb::inspect && movement::wire::Zero(&c.expected, sizeof(c.expected)))
        || (v == Verb::open && ValidSnapshot(c.expected) && !c.expected.loading);
}
}
