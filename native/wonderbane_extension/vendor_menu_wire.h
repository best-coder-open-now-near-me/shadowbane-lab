#pragma once
#include "vendor_wire.h"
namespace wonderbane::extension::vendor_menu::wire {
using Outcome = vendor::wire::Outcome;
enum class Verb : std::uint32_t { inspect = 25, open_recipe = 26, select_recipe = 27,
    random_mode = 28, close_recipe = 29, open_inventory = 30, close_inventory = 31 };
constexpr std::uint32_t magic = 0x57424d31, ready = 1, in_flight = 2, unresolved = 4;
#pragma pack(push, 1)
struct Snapshot {
    std::uint64_t scene = 0, revision = 0;
    std::uint32_t root = 0, manager = 0, front_hud = 0, menu = 0, hireling = 0;
    std::uint32_t building = 0, vendor = 0, recipe = 0, inventory = 0, item_template = 0;
    std::uint32_t prefix = 0, suffix = 0, mode = 0, table = 0, quantity = 0, multiple = 0;
    std::uint32_t selected_template = 0, activated_template = 0, sentinel = 0, recipe_list = 0;
};
struct Command {
    movement::wire::Host host{};
    std::uint64_t window = 0;
    std::array<std::uint8_t, 16> request{};
    Snapshot expected{};
    std::uint32_t item_template = 0;
    std::uint8_t reserved[436]{};
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
inline bool Equal(const Snapshot& a, const Snapshot& b) noexcept { return !std::memcmp(&a, &b, sizeof(a)); }
inline bool ValidSnapshot(const Snapshot& s) noexcept {
    if (!s.scene || !s.revision || !s.root || !s.manager || !s.menu || !s.hireling
        || !s.building || !s.vendor || s.multiple > 1 || s.mode > 2) { return false; }
    if (!s.recipe) {
        return !s.item_template && !s.prefix && !s.suffix && !s.mode && !s.table && !s.quantity
            && !s.multiple && !s.selected_template && !s.activated_template && !s.sentinel && !s.recipe_list;
    }
    return s.recipe_list && s.sentinel == 3362971591U;
}
inline bool SameOwner(const Snapshot& a, const Snapshot& b) noexcept {
    return a.scene == b.scene && a.root == b.root && a.manager == b.manager
        && a.menu == b.menu && a.hireling == b.hireling && a.building == b.building && a.vendor == b.vendor;
}
inline bool Selected(const Snapshot& s, std::uint32_t id) noexcept {
    return id && s.recipe && s.front_hud == s.recipe && s.item_template == id
        && s.selected_template == id && s.activated_template == id;
}
inline bool Reached(Verb verb, const Command& c, const Snapshot& s) noexcept {
    if (!ValidSnapshot(s) || !SameOwner(c.expected, s)) { return false; }
    switch (verb) {
    case Verb::open_recipe: return s.recipe && s.front_hud == s.recipe && !s.multiple;
    case Verb::select_recipe: return s.recipe == c.expected.recipe
        && s.recipe_list == c.expected.recipe_list && Selected(s, c.item_template);
    case Verb::random_mode: return s.recipe == c.expected.recipe && s.recipe_list == c.expected.recipe_list
        && Selected(s, c.expected.item_template) && s.mode == 1 && s.table
        && s.prefix == s.sentinel && s.suffix == s.sentinel && s.quantity == 1 && !s.multiple;
    case Verb::close_recipe: return !s.recipe && s.front_hud == s.menu;
    case Verb::open_inventory: return s.inventory && s.front_hud == s.inventory;
    case Verb::close_inventory: return !s.inventory && s.front_hud == s.menu;
    default: return false;
    }
}
inline bool Valid(Verb verb, const Command& c) noexcept {
    if (!movement::wire::Valid(c.host) || !c.window || c.window > UINT32_MAX
        || movement::wire::Zero(c.request.data(), c.request.size())
        || !movement::wire::Zero(c.reserved, sizeof(c.reserved))) { return false; }
    if (verb == Verb::inspect) { return !c.item_template && movement::wire::Zero(&c.expected, sizeof(c.expected)); }
    if (!ValidSnapshot(c.expected) || (verb != Verb::select_recipe && c.item_template)) { return false; }
    const auto& s = c.expected;
    switch (verb) {
    case Verb::open_recipe: return !s.inventory && (s.front_hud == s.menu || (s.recipe && s.front_hud == s.recipe && !s.multiple));
    case Verb::select_recipe: return c.item_template && s.recipe && s.front_hud == s.recipe && !s.multiple;
    case Verb::random_mode: return Selected(s, s.item_template) && !s.multiple;
    case Verb::close_recipe: return !s.inventory && (s.front_hud == s.menu || (s.recipe && s.front_hud == s.recipe));
    case Verb::open_inventory: return !s.recipe && (s.front_hud == s.menu || (s.inventory && s.front_hud == s.inventory));
    case Verb::close_inventory: return !s.recipe && (s.front_hud == s.menu || (s.inventory && s.front_hud == s.inventory));
    default: return false;
    }
}
}
