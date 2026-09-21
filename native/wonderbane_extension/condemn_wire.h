#pragma once
#include "condemn_native.h"
#include "vendor_wire.h"
namespace wonderbane::extension::condemn::wire {
using Outcome = vendor::wire::Outcome;
enum class Verb : std::uint32_t { inspect = 23, ensure = 24 };
enum class Phase : std::uint32_t { idle, opening, adding, enabling, verified, uncertain, existing };
constexpr std::uint32_t magic = 0x57424b31, ready = 1, in_flight = 2, unresolved = 4;
#pragma pack(push, 1)
struct Target {
    native::Key building{}, identity{};
    std::uint32_t scope = 0;
    bool operator==(const Target&) const = default;
};
struct Snapshot {
    std::uint64_t scene = 0, revision = 0;
    native::Key local{};
    std::uint32_t root = 0, manager = 0, building_hud = 0, front = 0, open_button = 0;
    native::Key building{};
    std::uint32_t kos = 0, list = 0, selected = 0, list_selected = 0, count = 0;
    native::Key context{};
    std::array<native::Key, 3> pending{};
    std::uint32_t flags = 0, row = 0, entry = 0, enabled = 0, collision = 0;
    native::Key entry_key{};
};
struct Command {
    movement::wire::Host host{};
    std::uint64_t window = 0;
    std::array<std::uint8_t, 16> request{};
    Target target{};
    Snapshot expected{};
    std::array<std::uint8_t, 16> transition_request{};
    std::uint8_t reserved[368]{};
};
struct Receipt {
    std::array<std::uint8_t, 16> request{};
    movement::wire::Host host{};
    std::uint64_t window = 0;
    std::uint32_t outcome = 0, flags = 0;
    Snapshot snapshot{};
    Target target{}, transition_target{};
    std::array<std::uint8_t, 16> transition_request{};
    std::uint32_t phase = 0, signature = magic;
    // Most recent action's admission floor/tick; completion is a keyed state
    // observation, never a server-echoed request UUID.
    std::uint64_t action_tick = 0, response_floor = 0, completion_sequence = 0;
    std::uint8_t reserved[116]{};
};
#pragma pack(pop)
static_assert(sizeof(Target) == 20 && sizeof(Snapshot) == 132);
static_assert(sizeof(Command) == 576 && sizeof(Receipt) == 384);
inline native::Target Decode(const Target& t) noexcept { return {t.building, t.identity, t.scope}; }
inline Snapshot Encode(const native::Snapshot& s, std::uint64_t revision) noexcept {
    return {s.scene, revision, s.local, s.root, s.manager, s.building_hud, s.front, s.open_button,
        s.building, s.kos, s.list, s.selected, s.list_selected, s.count, s.context, s.pending,
        s.flags, s.row, s.entry, s.enabled, s.collision, s.entry_key};
}
inline bool Equal(const Snapshot& a, const Snapshot& b) noexcept { return !std::memcmp(&a, &b, sizeof(a)); }
inline bool Typed(native::Key k, unsigned type) noexcept { return k[0] && k[1] == type; }
inline bool Owned(const Target& t, const Snapshot& s) noexcept {
    return s.scene && s.revision && Typed(s.local, 53) && s.root && s.manager && s.building_hud
        && s.building == t.building && s.enabled <= 1 && !s.collision && s.count <= 512;
}
inline bool List(const Target& t, const Snapshot& s) noexcept {
    return Owned(t, s) && s.kos && s.list && s.front == s.kos && s.context == t.building && !s.flags;
}
inline bool Eligible(const Target& t, const Snapshot& s) noexcept {
    if (!Owned(t, s)) { return false; }
    if (s.front == s.building_hud && s.open_button) { return true; }
    return List(t, s) && (s.entry ? s.row && Typed(s.entry_key, 23) : s.count < 512 && !s.row && !s.enabled && s.entry_key == native::Key{});
}
inline bool Valid(Verb verb, const Command& c) noexcept {
    if (!movement::wire::Valid(c.host) || !c.window || c.window > UINT32_MAX
        || movement::wire::Zero(c.request.data(), c.request.size())
        || (!Typed(c.target.building, 8) || !Typed(c.target.identity, 23) || (c.target.scope != 4 && c.target.scope != 5)) || !movement::wire::Zero(c.reserved, sizeof(c.reserved))) { return false; }
    if (verb == Verb::inspect) { return movement::wire::Zero(&c.expected, sizeof(c.expected)); }
    return verb == Verb::ensure && Eligible(c.target, c.expected)
        && movement::wire::Zero(c.transition_request.data(), c.transition_request.size());
}
}
