#include "city_window_controller.h"
#undef NDEBUG
#include <cassert>
#include <cstdio>
namespace c = wonderbane::extension::city_window;
namespace w = c::wire;
struct Fake final : c::Invoker {
    unsigned calls = 0;
    w::Outcome outcome = w::Outcome::submitted;
    w::Outcome Open(const w::Snapshot&) noexcept override { ++calls; return outcome; }
};
w::Snapshot State() { w::Snapshot s{}; s.scene = 1; s.root = 100; s.manager = 200; return s; }
w::Command Request(const c::Controller& c, unsigned id = 1) {
    w::Command r{}; r.host = {1, 1, 1}; r.window = 1000;
    std::memcpy(r.request.data(), &id, sizeof(id)); r.expected = c.Current(); return r;
}
bool Is(const w::Receipt& r, w::Outcome o) { return r.outcome == static_cast<unsigned>(o); }
int main(int argc, char**) {
    c::Controller controller; Fake invoker; controller.Observe(State(), true);
    auto command = Request(controller);
    if (argc > 1) {
        auto print = [](const auto& obj) {
            for (auto p = reinterpret_cast<const unsigned char*>(&obj);
                 p != reinterpret_cast<const unsigned char*>(&obj) + sizeof(obj); ++p) { std::printf("%02x", *p); }
            std::printf("\n");
        };
        print(command.expected); print(command);
        print(controller.Execute(w::Verb::open, command, true, true, invoker)); return 0;
    }
    assert(Is(controller.Execute(w::Verb::open, command, false, true, invoker), w::Outcome::stale));
    assert(Is(controller.Execute(w::Verb::open, command, true, false, invoker), w::Outcome::unavailable));
    auto wrong = command; ++wrong.expected.manager;
    assert(Is(controller.Execute(w::Verb::open, wrong, true, true, invoker), w::Outcome::stale));
    assert(!invoker.calls);
    auto r = controller.Execute(w::Verb::open, command, true, true, invoker);
    assert(Is(r, w::Outcome::submitted) && !r.flags && invoker.calls == 1);
    assert(Is(controller.Execute(w::Verb::open, command, true, true, invoker), w::Outcome::submitted));
    assert(Is(controller.Execute(w::Verb::open, wrong, true, true, invoker), w::Outcome::invalid));
    assert(invoker.calls == 1);
    auto state = State(); state.hud = 300; state.visible = 1; state.mode = 2;
    state.active_manager = state.manager; state.loading = 1;
    controller.Observe(state, true);
    command = Request(controller, 2); command.expected = {};
    r = controller.Execute(w::Verb::inspect, command, true, true, invoker);
    assert(Is(r, w::Outcome::observed) && !r.flags && r.snapshot.loading);
    command = Request(controller, 3);
    assert(!w::Valid(w::Verb::open, command));
    state.loading = 0; controller.Observe(state, true); command = Request(controller, 4);
    assert(Is(controller.Execute(w::Verb::open, command, true, true, invoker), w::Outcome::observed));
    assert(invoker.calls == 1); // Already open cannot send a second discovery request.
    controller.Observe({}, false);
    command = Request(controller, 5); command.expected = {};
    assert(!controller.Execute(w::Verb::inspect, command, true, true, invoker).flags);
    assert(!w::Valid(static_cast<w::Verb>(13), command));
    c::Controller exhausted; exhausted.Observe(State(), true);
    for (unsigned i = 1; i <= 4096; ++i) {
        auto next = Request(exhausted, i);
        assert(Is(exhausted.Execute(w::Verb::open, next, true, true, invoker), w::Outcome::submitted));
    }
    assert(Is(exhausted.Execute(w::Verb::open, Request(exhausted, 4097), true, true, invoker), w::Outcome::exhausted));
    c::Controller uncertain; uncertain.Observe(State(), true); invoker.outcome = w::Outcome::uncertain;
    command = Request(uncertain); const auto before = invoker.calls;
    assert(Is(uncertain.Execute(w::Verb::open, command, true, true, invoker), w::Outcome::uncertain));
    assert(Is(uncertain.Execute(w::Verb::open, command, true, true, invoker), w::Outcome::uncertain));
    assert(invoker.calls == before + 1);
}
