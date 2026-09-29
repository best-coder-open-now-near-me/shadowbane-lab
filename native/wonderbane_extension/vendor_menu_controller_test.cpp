#include "vendor_menu_controller.h"
#undef NDEBUG
#include <cassert>
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>
namespace m = wonderbane::extension::vendor_menu;
namespace w = m::wire;
struct Invoker final : m::Invoker {
    unsigned calls = 0;
    w::Outcome result = w::Outcome::submitted;
    w::Outcome Invoke(w::Verb, const w::Command&) noexcept override { ++calls; return result; }
};
static w::Snapshot Menu() {
    w::Snapshot s{}; s.scene = 1; s.revision = 1; s.root = 100; s.manager = 200;
    s.front_hud = s.menu = 300; s.hireling = 400; s.building = 500; s.vendor = 600; return s;
}
static w::Snapshot Recipe() {
    auto s = Menu(); s.recipe = s.front_hud = 700; s.recipe_list = 701;
    s.item_template = s.selected_template = s.activated_template = 5051080;
    s.sentinel = s.prefix = s.suffix = 3362971591U; s.mode = 1; s.table = 16; s.quantity = 1; return s;
}
static w::Command Command(const w::Snapshot& s, unsigned id = 1) {
    w::Command c{}; c.host = {1, 2, 3}; c.window = 123; c.request[0] = static_cast<std::uint8_t>(id); c.expected = s; return c;
}
static std::string Hex(const void* data, std::size_t size) {
    const auto* bytes = static_cast<const unsigned char*>(data);
    std::string out; out.reserve(size * 2);
    for (std::size_t i = 0; i < size; ++i) {
        constexpr char digits[] = "0123456789abcdef";
        out += digits[bytes[i] >> 4]; out += digits[bytes[i] & 15];
    }
    return out;
}
int main(int argc, char** argv) {
    Invoker i;
    m::Controller c;
    c.Observe(Menu(), true, 10);
    auto open = Command(c.Current());
    assert(w::Valid(w::Verb::open_recipe, open));
    auto r = c.Execute(w::Verb::open_recipe, open, true, true, 10, i);
    assert(i.calls == 1 && c.Busy() && r.flags == w::in_flight);
    // A retained submission is immutable; replay never dispatches or claims completion.
    c.Observe(Recipe(), true, 11);
    assert(!c.Busy());
    auto replay = c.Execute(w::Verb::open_recipe, open, true, true, 12, i);
    assert(i.calls == 1 && !std::memcmp(&r, &replay, sizeof(r)));
    w::Command inspect{}; inspect.host = open.host; inspect.window = open.window; inspect.request[0] = 99;
    auto observed = c.Execute(w::Verb::inspect, inspect, true, true, 12, i);
    assert(observed.transition_request == open.request && observed.flags == w::ready);
    auto select = Command(c.Current(), 2); select.item_template = 25860;
    assert(w::Valid(w::Verb::select_recipe, select));
    c.Execute(w::Verb::select_recipe, select, true, true, 13, i);
    auto highlighted = Recipe(); highlighted.selected_template = 25860;
    c.Observe(highlighted, true, 14);
    assert(c.Busy()); // Highlight alone must not complete a requested recipe.
    highlighted.item_template = highlighted.activated_template = 25860;
    c.Observe(highlighted, true, 15);
    assert(!c.Busy());
    auto magic = Command(c.Current(), 3);
    r = c.Execute(w::Verb::random_mode, magic, true, true, 16, i);
    assert(r.outcome == static_cast<unsigned>(w::Outcome::observed) && i.calls == 2);
    assert(r.transition_request == magic.request && r.flags == w::ready);
    auto wrong_request = magic; wrong_request.item_template = 25860;
    assert(!w::Valid(w::Verb::random_mode, wrong_request));
    auto close = Command(c.Current(), 4);
    c.Execute(w::Verb::close_recipe, close, true, true, 17, i);
    auto covered = Menu(); covered.front_hud = 999;
    c.Observe(covered, true, 18); assert(c.Busy());
    c.Observe(Menu(), true, 19); assert(!c.Busy());
    auto inventory = Command(c.Current(), 5);
    c.Execute(w::Verb::open_inventory, inventory, true, true, 20, i);
    auto opened = Menu(); opened.inventory = 800; opened.front_hud = 800;
    c.Observe(opened, true, 21); assert(!c.Busy());
    auto inv_close = Command(c.Current(), 6);
    c.Execute(w::Verb::close_inventory, inv_close, true, true, 22, i);
    c.Observe(Menu(), true, 23); assert(!c.Busy());
    auto stale = Command(Menu(), 7);
    r = c.Execute(w::Verb::open_recipe, stale, true, true, 24, i);
    assert(r.outcome == static_cast<unsigned>(w::Outcome::stale));
    const auto calls = i.calls;
    for (bool change_owner : {false, true}) {
        m::Controller pending; pending.Observe(Menu(), true, 100);
        auto command = Command(pending.Current());
        pending.Execute(w::Verb::open_recipe, command, true, true, 100, i);
        auto after = Recipe(); if (change_owner) { ++after.vendor; }
        pending.Observe(after, true, change_owner ? 101 : 5101);
        assert(pending.Busy());
        auto result = pending.Execute(w::Verb::inspect, inspect, true, true, 5102, i);
        assert(result.flags & w::unresolved);
        pending.Observe(Recipe(), true, 5103);
        assert(pending.Busy()); // Late local state never clears uncertainty.
    }
    assert(i.calls == calls + 2);
    for (auto failure : {w::Outcome::stale, w::Outcome::unavailable, w::Outcome::uncertain}) {
        m::Controller fail; fail.Observe(Menu(), true, 1); auto command = Command(fail.Current());
        i.result = failure; auto original = fail.Execute(w::Verb::open_recipe, command, true, true, 2, i);
        assert(fail.Busy() == (failure == w::Outcome::uncertain));
        auto duplicate = fail.Execute(w::Verb::open_recipe, command, true, true, 3, i);
        assert(!std::memcmp(&original, &duplicate, sizeof(original)));
    }
    for (bool replace_list : {false, true}) {
        m::Controller replacement; replacement.Observe(Recipe(), true, 10);
        auto command = Command(replacement.Current()); command.item_template = 25860;
        i.result = w::Outcome::submitted;
        replacement.Execute(w::Verb::select_recipe, command, true, true, 11, i);
        auto after = Recipe(); after.item_template = after.selected_template = after.activated_template = 25860;
        if (replace_list) { ++after.recipe_list; }
        else { ++after.recipe; after.front_hud = after.recipe; }
        assert(!w::Reached(w::Verb::select_recipe, command, after));
        replacement.Observe(after, true, 12);
        assert(replacement.Execute(w::Verb::inspect, inspect, true, true, 13, i).flags & w::unresolved);
    }
    auto invalid = Recipe(); invalid.recipe = 0; assert(!w::ValidSnapshot(invalid));
    invalid = Recipe(); invalid.sentinel = 0; assert(!w::ValidSnapshot(invalid));
    auto wrong = Command(Menu()); wrong.item_template = 25860; assert(!w::Valid(w::Verb::open_recipe, wrong));
    wrong = Command(Recipe()); wrong.expected.multiple = 1; wrong.item_template = 25860;
    assert(!w::Valid(w::Verb::select_recipe, wrong));
    wrong = Command(Menu()); wrong.reserved[0] = 1; assert(!w::Valid(w::Verb::open_recipe, wrong));
    wrong = Command(Menu()); assert(!w::Valid(static_cast<w::Verb>(32), wrong));
    wrong = Command(Recipe()); wrong.expected.activated_template = 0; assert(!w::Valid(w::Verb::random_mode, wrong));
    auto fixture_command = Command(Recipe()); fixture_command.item_template = 25860;
    w::Receipt fixture_receipt{}; fixture_receipt.request = fixture_command.request;
    fixture_receipt.host = fixture_command.host; fixture_receipt.window = fixture_command.window;
    fixture_receipt.flags = w::ready; fixture_receipt.snapshot = Recipe();
    fixture_receipt.transition_request = fixture_command.request;
    const auto fixture = Hex(&fixture_command, sizeof(fixture_command)) + "\n"
        + Hex(&fixture_receipt, sizeof(fixture_receipt)) + "\n";
    if (argc == 2) {
        if (!std::strcmp(argv[1], "--emit")) { std::cout << fixture; }
        else {
            std::ifstream file(argv[1]); assert(file.good());
            const std::string expected{std::istreambuf_iterator<char>(file), std::istreambuf_iterator<char>()};
            assert(expected == fixture);
        }
    }
}
