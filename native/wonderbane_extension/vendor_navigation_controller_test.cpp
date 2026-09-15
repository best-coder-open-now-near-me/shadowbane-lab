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
    n::Controller controller; Fake invoker; controller.Observe(State(), true, 10);
    auto command = Request(controller);
    if (argc > 1) {
        auto print = [](const auto& obj) {
            for (auto* p = reinterpret_cast<const unsigned char*>(&obj);
                p != reinterpret_cast<const unsigned char*>(&obj) + sizeof(obj); ++p) { std::printf("%02x", *p); }
            std::printf("\n");
        };
        print(command.expected); print(command);
        print(controller.Execute(w::Verb::building, command, true, true, 10, invoker)); return 0;
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
    state.building = {456, 8}; state.active_manager = state.manager;
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
    state.vendor_hud = 500; state.visible = 3;
    controller.Observe(state, true, 103); assert(!controller.Busy());
    next = Request(controller, 5); next.vendor = state.vendor;
    assert(Is(controller.Execute(w::Verb::vendor, next, true, true, 104, invoker), w::Outcome::observed));
    assert(invoker.calls == 2);
    auto inspect = next; inspect.expected = {}; inspect.building = {}; inspect.vendor = {};
    assert(controller.Execute(w::Verb::inspect, inspect, true, true, 104, invoker).flags == w::ready);
    auto bad = next; bad.vendor[1] = 8; assert(!w::Valid(w::Verb::vendor, bad));
    bad = next; bad.expected.offline = 1; assert(!w::Valid(w::Verb::vendor, bad));
    bad = next; bad.reserved[0] = 1; assert(!w::Valid(w::Verb::vendor, bad));
    for (int mode = 0; mode < 3; ++mode) {
        n::Controller stopped; stopped.Observe(State(), true, 10);
        invoker.outcome = mode == 2 ? w::Outcome::uncertain : w::Outcome::submitted;
        auto c = Request(stopped); stopped.Execute(w::Verb::building, c, true, true, 10, invoker);
        auto response = state;
        if (mode == 1) { response.scene = 2; } // Scene replacement.
        stopped.Observe(response, true, mode == 0 ? 10011 : 11);
        auto read = inspect; auto observed = stopped.Execute(w::Verb::inspect, read, true, true, 10012, invoker);
        assert(stopped.Busy() && (observed.flags & w::unresolved) && !(observed.flags & w::ready));
        // A late matching window cannot silently clear uncertainty.
        stopped.Observe(state, true, 10013); assert(stopped.Busy());
        auto retry = Request(stopped, 44);
        assert(Is(stopped.Execute(w::Verb::building, retry, true, true, 10013, invoker), w::Outcome::pending));
    }
    n::Controller bounded; bounded.Observe(state, true, 10);
    for (unsigned i = 1; i <= 4096; ++i) {
        auto c = Request(bounded, i);
        assert(Is(bounded.Execute(w::Verb::building, c, true, true, 10, invoker), w::Outcome::observed));
    }
    assert(Is(bounded.Execute(w::Verb::building, Request(bounded, 4097), true, true, 10, invoker), w::Outcome::exhausted));
}
