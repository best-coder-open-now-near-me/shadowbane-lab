#pragma once
#include "vendor_navigation_wire.h"
namespace wonderbane::extension::guard_funding::wire {
using Outcome = vendor::wire::Outcome;
using Key = vendor_navigation::wire::Key;
enum class Verb : std::uint32_t { inspect = 19, transfer = 20 };
enum class Direction : std::uint32_t { warehouse = 1, structure = 2 };
constexpr std::uint32_t magic = 0x57424631, ready = 1, in_flight = 2, unresolved = 4;
#pragma pack(push, 1)
struct Snapshot {
    std::uint64_t scene = 0, revision = 0;
    std::uint32_t root = 0, actor = 0;
    Key character{};
    std::uint32_t manager = 0, hud = 0, source_object = 0;
    Key source{};
    std::uint32_t direction = 0, resource = 0, balance = 0, reserve = 0, purse = 0;
    std::uint32_t quote = 0, limit = 0, entered = 0, accept = 0, cancel = 0, helper = 0;
};
struct Command {
    movement::wire::Host host{};
    std::uint64_t window = 0;
    std::array<std::uint8_t, 16> request{};
    Snapshot expected{};
    std::uint32_t direction = 0, amount = 0;
    std::uint8_t reserved[432]{};
};
struct Receipt {
    std::array<std::uint8_t, 16> request{};
    movement::wire::Host host{};
    std::uint64_t window = 0;
    std::uint32_t outcome = 0, flags = 0;
    Snapshot snapshot{};
    std::array<std::uint8_t, 16> transition_request{};
    std::uint32_t signature = magic;
    std::uint8_t reserved[220]{};
};
#pragma pack(pop)
static_assert(sizeof(Snapshot) == 96 && sizeof(Command) == 576 && sizeof(Receipt) == 384);
inline bool DirectionValid(std::uint32_t d) noexcept { return d == 1 || d == 2; }
inline bool Equal(const Snapshot& a, const Snapshot& b) noexcept { return !std::memcmp(&a, &b, sizeof(a)); }
inline bool ValidSnapshot(const Snapshot& s) noexcept {
    if (!s.scene || !s.revision || !s.root || !s.actor || !s.character[0] || !s.character[1]
        || !s.manager || !s.hud || !s.source[0] || !DirectionValid(s.direction)
        || s.balance > INT32_MAX || s.reserve > INT32_MAX || s.purse > INT32_MAX) { return false; }
    if (s.direction == 1 ? (!s.source_object || s.source[1] != 42 || !s.resource)
        : (s.source_object || s.source[1] != 8 || s.resource || s.reserve)) { return false; }
    if (!s.quote) { return !s.limit && !s.entered && !s.accept && !s.cancel && !s.helper; }
    if (s.quote == s.hud || !s.accept || !s.cancel || !s.helper || s.accept == s.cancel
        || s.accept == s.helper || s.cancel == s.helper || s.limit > INT32_MAX || s.entered > s.limit) { return false; }
    const auto available = s.balance > s.reserve ? s.balance - s.reserve : 0;
    return s.direction == 1 ? s.limit == available : s.limit == s.purse;
}
inline bool Eligible(const Snapshot& s, std::uint32_t amount) noexcept {
    return ValidSnapshot(s) && s.quote && amount && amount <= s.limit
        && (s.direction == 1 ? amount <= INT32_MAX - s.purse : amount <= INT32_MAX - s.balance);
}
inline bool SameOwner(const Snapshot& a, const Snapshot& b) noexcept {
    return a.scene == b.scene && a.root == b.root && a.actor == b.actor && a.character == b.character
        && a.manager == b.manager && a.hud == b.hud && a.source_object == b.source_object
        && a.source == b.source && a.direction == b.direction && a.resource == b.resource;
}
inline bool Confirmed(const Command& c, const Snapshot& s) noexcept {
    if (!ValidSnapshot(s) || !SameOwner(c.expected, s) || s.reserve != c.expected.reserve || s.quote) { return false; }
    return c.direction == 1
        ? s.balance == c.expected.balance - c.amount && s.purse == c.expected.purse + c.amount
        : s.balance == c.expected.balance + c.amount && s.purse == c.expected.purse - c.amount;
}
inline bool Valid(Verb verb, const Command& c) noexcept {
    if (!movement::wire::Valid(c.host) || !c.window || c.window > UINT32_MAX
        || !DirectionValid(c.direction) || movement::wire::Zero(c.request.data(), c.request.size())
        || !movement::wire::Zero(c.reserved, sizeof(c.reserved))) { return false; }
    if (verb == Verb::inspect) { return !c.amount && movement::wire::Zero(&c.expected, sizeof(c.expected)); }
    return verb == Verb::transfer && c.direction == c.expected.direction && Eligible(c.expected, c.amount);
}
}
