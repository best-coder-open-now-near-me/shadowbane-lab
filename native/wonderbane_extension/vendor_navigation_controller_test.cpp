#include "vendor_navigation_controller.h"
#undef NDEBUG
#include <cassert>
#include <cstdio>
namespace n = wonderbane::extension::vendor_navigation;
namespace w = n::wire;
struct Fake final : n::Invoker {
    unsigned calls = 0; w::Outcome outcome = w::Outcome::submitted;
    w::Outcome Open(w::Verb, const w::Command&) noexcept override { ++calls; return outcome; }
};
w::Snapshot State() { w::Snapshot s{}; s.scene = 1; s.root = 100; s.manager = 200; return s; }
w::Command Request(n::Controller& c, unsigned id = 1) {
    w::Command r{}; r.host = {1, 1, 1}; r.window = 1000; r.building = {123, 8};
    std::memcpy(r.request.data(), &id, sizeof(id)); r.expected = c.Current(); return r;
}
bool Is(const w::Receipt& r, w::Outcome o) { return r.outcome == static_cast<unsigned>(o); }
int main(int argc, char**) {
    n::Controller controller; Fake invoker;
    auto initial = State();
    if (argc > 2) {
        initial.mode = 6; initial.building_hud = 300; initial.visible = initial.initialized = 1;
        initial.building = {123, 8}; initial.warehouse_hud = 600;
        initial.warehouse_object = 700; initial.warehouse = {777, 42}; initial.front_hud = 600;
    }
    controller.Observe(initial, true, 10);
    auto command = Request(controller);
    if (argc > 2) { command.vendor = {777, 42}; }
    if (argc > 1) {
        auto print = [](const auto& obj) {
            for (auto* p = reinterpret_cast<const unsigned char*>(&obj);
                p != reinterpret_cast<const unsigned char*>(&obj) + sizeof(obj); ++p) { std::printf("%02x", *p); }
            std::printf("\n");
        };
        print(command.expected); print(command);
        print(controller.Execute(argc > 2 ? w::Verb::warehouse : w::Verb::building, command, true, true, 10, invoker)); return 0;
    }
    assert(Is(controller.Execute(w::Verb::building, command, false, true, 10, invoker), w::Outcome::stale));
    assert(Is(controller.Execute(w::Verb::building, command, true, false, 10, invoker), w::Outcome::unavailable));
    auto wrong = command; ++wrong.expected.manager;
    assert(Is(controller.Execute(w::Verb::building, wrong, true, true, 10, invoker), w::Outcome::stale));
    auto r = controller.Execute(w::Verb::building, command, true, true, 10, invoker);
    assert(Is(r, w::Outcome::submitted) && r.flags == w::in_flight && controller.Busy() && invoker.calls == 1);
    assert(r.transition_request == command.request);
    assert(Is(controller.Execute(w::Verb::building, command, true, true, 11, invoker), w::Outcome::submitted));
    assert(Is(controller.Execute(w::Verb::building, wrong, true, true, 11, invoker), w::Outcome::invalid));
    auto next = Request(controller, 2);
    assert(Is(controller.Execute(w::Verb::building, next, true, true, 11, invoker), w::Outcome::pending));
    assert(invoker.calls == 1);
    auto state = State(); state.mode = 6; state.building_hud = 300; state.initialized = state.visible = 1;
    state.building = {456, 8}; state.front_hud = 300;
    controller.Observe(state, true, 100); assert(controller.Busy()); // Wrong response cannot resolve.
    state.selected_entry = 350; // A selected vacancy still permits building confirmation.
    state.building = command.building; controller.Observe(state, true, 101); assert(!controller.Busy());
    next = Request(controller, 3);
    assert(Is(controller.Execute(w::Verb::building, next, true, true, 101, invoker), w::Outcome::observed));
    assert(invoker.calls == 1); // Already-open exact key is a no-op.
    next = Request(controller, 4); next.vendor = {777, 42};
    assert(Is(controller.Execute(w::Verb::vendor, next, true, true, 101, invoker), w::Outcome::submitted));
    assert(invoker.calls == 2);
    state.selected_entry = 400; state.vendor = next.vendor; // Selection alone is not a response.
    controller.Observe(state, true, 102); assert(controller.Busy());
    state.vendor_hud = 500; state.visible = 3; state.front_hud = 500;
    controller.Observe(state, true, 103); assert(!controller.Busy());
    next = Request(controller, 5); next.vendor = state.vendor;
    assert(Is(controller.Execute(w::Verb::vendor, next, true, true, 104, invoker), w::Outcome::observed));
    assert(invoker.calls == 2);
    auto inspect = next; inspect.expected = {}; inspect.building = {}; inspect.vendor = {};
    assert(controller.Execute(w::Verb::inspect, inspect, true, true, 104, invoker).flags == w::ready);
    auto bad = next; bad.vendor[1] = 8; assert(!w::Valid(w::Verb::vendor, bad));
    bad = next; bad.expected.offline = 1; assert(!w::Valid(w::Verb::vendor, bad));
    bad = next; bad.reserved[0] = 1; assert(!w::Valid(w::Verb::vendor, bad));
    n::Controller guards; Fake guard_invoker;
    guards.Observe(state, true, 200);
    auto guard = Request(guards, 10); guard.vendor = {777, 37};
    assert(!w::Valid(w::Verb::vendor, guard) && w::Valid(w::Verb::guard, guard));
    auto vendor = guard; vendor.vendor[1] = 42;
    assert(!w::Valid(w::Verb::guard, vendor));
    assert(Is(guards.Execute(w::Verb::guard, guard, true, true, 200, guard_invoker), w::Outcome::submitted));
    guards.Observe(state, true, 201); assert(guards.Busy()); // Same ID, wrong key type.
    auto guard_state = state; guard_state.vendor = guard.vendor;
    guard_state.visible = 1; guards.Observe(guard_state, true, 202); assert(guards.Busy());
    guard_state.visible = 3; guards.Observe(guard_state, true, 203); assert(!guards.Busy());
    assert(!w::Opened(guard_state, w::Verb::vendor, {123, 8}, guard.vendor));
    assert(w::Opened(guard_state, w::Verb::guard, {123, 8}, guard.vendor));
    assert(Is(guards.Execute(w::Verb::guard, guard, true, true, 204, guard_invoker), w::Outcome::submitted));
    assert(guard_invoker.calls == 1); // Original receipt, no replay.
    auto already = Request(guards, 11); already.vendor = guard.vendor;
    assert(Is(guards.Execute(w::Verb::guard, already, true, true, 204, guard_invoker), w::Outcome::observed));
    assert(guard_invoker.calls == 1);
    n::Controller warehouses; Fake warehouse_invoker;
    warehouses.Observe(state, true, 300);
    auto warehouse_request = Request(warehouses, 12); warehouse_request.vendor = {777, 42};
    assert(w::Valid(w::Verb::warehouse, warehouse_request));
    auto wrong_type = warehouse_request; wrong_type.vendor[1] = 37;
    assert(!w::Valid(w::Verb::warehouse, wrong_type));
    auto missing_building = warehouse_request; missing_building.expected.visible = 0;
    assert(!w::Valid(w::Verb::warehouse, missing_building));
    assert(Is(warehouses.Execute(w::Verb::warehouse, warehouse_request, true, true, 300, warehouse_invoker), w::Outcome::submitted));
    warehouses.Observe(state, true, 301); assert(warehouses.Busy()); // Management inventory cannot complete it.
    auto warehouse_state = state; warehouse_state.warehouse_hud = 600;
    warehouse_state.warehouse_object = 700; warehouse_state.warehouse = {888, 42}; warehouse_state.front_hud = 600;
    warehouses.Observe(warehouse_state, true, 302); assert(warehouses.Busy());
    warehouse_state.warehouse = {777, 42}; warehouse_state.building = {456, 8};
    warehouses.Observe(warehouse_state, true, 303); assert(warehouses.Busy());
    warehouse_state.building = {123, 8};
    warehouses.Observe(warehouse_state, true, 304); assert(!warehouses.Busy());
    assert(Is(warehouses.Execute(w::Verb::warehouse, warehouse_request, true, true, 305, warehouse_invoker), w::Outcome::submitted));
    auto existing = Request(warehouses, 13); existing.vendor = {777, 42};
    assert(Is(warehouses.Execute(w::Verb::warehouse, existing, true, true, 305, warehouse_invoker), w::Outcome::observed));
    assert(warehouse_invoker.calls == 1);
    for (const auto verb : {w::Verb::building, w::Verb::vendor, w::Verb::guard, w::Verb::warehouse}) {
        n::Controller focus; Fake focus_invoker;
        auto behind = state;
        behind.vendor = {777, verb == w::Verb::guard ? 37U : 42U};
        behind.warehouse_hud = 600; behind.warehouse_object = 700; behind.warehouse = {777, 42};
        behind.front_hud = 999;
        focus.Observe(behind, true, 400);
        auto c = Request(focus, 99);
        if (verb != w::Verb::building) { c.vendor = {777, verb == w::Verb::guard ? 37U : 42U}; }
        assert(!w::Opened(focus.Current(), verb, c.building, c.vendor));
        assert(Is(focus.Execute(verb, c, true, true, 400, focus_invoker), w::Outcome::submitted));
        assert(focus_invoker.calls == 1); // Owned in background is not an already-open no-op.
        focus.Observe(behind, true, 401); assert(focus.Busy());
        behind.front_hud = verb == w::Verb::building ? behind.building_hud
            : (verb == w::Verb::warehouse ? behind.warehouse_hud : behind.vendor_hud);
        focus.Observe(behind, true, 402); assert(!focus.Busy());
    }
    // Every menu family tolerates a slow server response without another dispatch.
    for (auto verb : {w::Verb::building, w::Verb::vendor, w::Verb::guard, w::Verb::warehouse}) {
        n::Controller delayed; Fake once;
        auto before = state; before.front_hud = 999;
        before.warehouse_hud = 600; before.warehouse_object = 700; before.warehouse = {777, 42};
        delayed.Observe(before, true, 10);
        auto c = Request(delayed, 70);
        if (verb != w::Verb::building) { c.vendor = {777, verb == w::Verb::guard ? 37U : 42U}; }
        assert(Is(delayed.Execute(verb, c, true, true, 10, once), w::Outcome::submitted));
        delayed.Observe(before, true, 15000);
        assert(delayed.Busy() && once.calls == 1);
        auto after = before;
        after.front_hud = verb == w::Verb::building ? after.building_hud
            : verb == w::Verb::warehouse ? after.warehouse_hud : after.vendor_hud;
        if (verb == w::Verb::guard) { after.vendor = c.vendor; }
        delayed.Observe(after, true, 45000);
        assert(!delayed.Busy() && once.calls == 1);
        auto receipt = delayed.Execute(w::Verb::inspect, inspect, true, true, 45001, once);
        assert(receipt.transition_request == c.request && receipt.flags == w::ready);
        assert(Is(delayed.Execute(verb, c, true, true, 45002, once), w::Outcome::submitted));
        assert(once.calls == 1); // Original submission is immutable; never replay.
    }
    for (int mode = 0; mode < 3; ++mode) {
        n::Controller stopped; stopped.Observe(State(), true, 10);
        invoker.outcome = mode == 2 ? w::Outcome::uncertain : w::Outcome::submitted;
        auto c = Request(stopped); stopped.Execute(w::Verb::building, c, true, true, 10, invoker);
        auto response = state;
        if (mode == 1) { response.scene = 2; } // Scene replacement.
        stopped.Observe(response, true, mode == 0 ? 60011 : 11);
        auto read = inspect; auto observed = stopped.Execute(w::Verb::inspect, read, true, true, 60012, invoker);
        assert(stopped.Busy() && (observed.flags & w::unresolved) && !(observed.flags & w::ready));
        // A late matching window cannot silently clear uncertainty.
        stopped.Observe(state, true, 60013); assert(stopped.Busy());
        auto retry = Request(stopped, 44);
        assert(Is(stopped.Execute(w::Verb::building, retry, true, true, 60013, invoker), w::Outcome::pending));
    }
    state.front_hud = state.building_hud;
    n::Controller bounded; bounded.Observe(state, true, 10);
    for (unsigned i = 1; i <= 4096; ++i) {
        auto c = Request(bounded, i);
        assert(Is(bounded.Execute(w::Verb::building, c, true, true, 10, invoker), w::Outcome::observed));
    }
    assert(Is(bounded.Execute(w::Verb::building, Request(bounded, 4097), true, true, 10, invoker), w::Outcome::exhausted));
}
