#include "guard_funding_controller.h"
#undef NDEBUG
#include <cassert>
#include <cstdio>
#include <string_view>
namespace f = wonderbane::extension::guard_funding;
using O = f::wire::Outcome;
struct Fake final : f::Invoker {
    unsigned calls = 0; O outcome = O::submitted;
    O Transfer(f::wire::Verb, const f::wire::Command&) noexcept override { ++calls; return outcome; }
};
f::wire::Snapshot State(std::uint32_t direction = 1) {
    f::wire::Snapshot s{}; s.scene = 1; s.revision = 1; s.root = 100; s.actor = 200; s.character = {300, 1};
    s.manager = 400; s.hud = 500; s.source_object = direction == 1 ? 600 : 0;
    s.source = {700, direction == 1 ? 42U : 8U}; s.direction = direction;
    s.resource = direction == 1 ? 800 : 0; s.balance = 1000; s.reserve = direction == 1 ? 50 : 0;
    s.purse = 500; s.quote = 900; s.limit = direction == 1 ? 950 : 500; s.entered = s.limit;
    s.accept = 1100; s.cancel = 1200; s.helper = 1300; return s;
}
f::wire::Command Command(std::uint32_t direction = 1) {
    f::wire::Command c{}; c.host = {1, 1, 1}; c.window = 1000; c.request[0] = 1;
    c.expected = State(direction); c.direction = direction; c.amount = 100; return c;
}
f::wire::Snapshot After(const f::wire::Command& c) {
    auto s = c.expected;
    s.quote = s.limit = s.entered = s.accept = s.cancel = s.helper = 0;
    if (c.direction == 1) { s.balance -= c.amount; s.purse += c.amount; }
    else { s.balance += c.amount; s.purse -= c.amount; }
    return s;
}
O Outcome(const f::wire::Receipt& r) { return static_cast<O>(r.outcome); }
void Hex(const void* data, std::size_t size) {
    auto* bytes = static_cast<const unsigned char*>(data);
    for (std::size_t i = 0; i < size; ++i) { std::printf("%02x", bytes[i]); } std::puts("");
}
int main(int argc, char** argv) {
    Fake invoker;
    if (argc == 2 && (std::string_view(argv[1]) == "wire" || std::string_view(argv[1]) == "wire-open")) {
        f::Controller controller; auto c = Command(); auto verb = f::wire::Verb::transfer;
        if (std::string_view(argv[1]) == "wire-open") {
            c.expected.quote = c.expected.limit = c.expected.entered = c.expected.accept = c.expected.cancel = c.expected.helper = 0;
            c.amount = 0; verb = f::wire::Verb::open_quote;
        }
        controller.Observe(1, c.expected, true, 1);
        const auto receipt = controller.Execute(verb, c, true, true, 1, invoker);
        Hex(&c.expected, sizeof(c.expected)); Hex(&c, sizeof(c)); Hex(&receipt, sizeof(receipt)); return 0;
    }
    for (std::uint32_t direction : {1U, 2U}) {
        const auto c = Command(direction); auto s = c.expected;
        assert(f::wire::Valid(f::wire::Verb::transfer, c));
        f::Controller controller; Fake calls;
        controller.Observe(direction, s, true, 1);
        auto receipt = controller.Execute(f::wire::Verb::transfer, c, true, true, 1, calls);
        assert(Outcome(receipt) == O::submitted && controller.Busy() && calls.calls == 1);
        auto repeat = controller.Execute(f::wire::Verb::transfer, c, true, true, 2, calls);
        assert(!std::memcmp(&receipt, &repeat, sizeof(receipt)) && calls.calls == 1);
        auto different = c; different.request[0] = 2;
        assert(Outcome(controller.Execute(f::wire::Verb::transfer, different, true, true, 2, calls)) == O::pending);
        auto partial = After(c); partial.purse = c.expected.purse;
        controller.Observe(direction, partial, true, 3); assert(controller.Busy());
        controller.Observe(direction, After(c), true, 4); assert(!controller.Busy());
        repeat = controller.Execute(f::wire::Verb::transfer, c, true, true, 5, calls);
        assert(!std::memcmp(&receipt, &repeat, sizeof(receipt)) && calls.calls == 1);
        auto inspect = c; inspect.expected = {}; inspect.amount = 0; inspect.request[0] = 3;
        receipt = controller.Execute(f::wire::Verb::inspect, inspect, true, false, 6, calls);
        assert(Outcome(receipt) == O::observed && receipt.transition_request == c.request && !receipt.flags);
        assert(f::wire::Confirmed(c, receipt.snapshot));
        for (unsigned fault = 0; fault < 7; ++fault) {
            f::Controller uncertain; Fake invoked; uncertain.Observe(direction, s, true, 1);
            uncertain.Execute(f::wire::Verb::transfer, c, true, true, 1, invoked);
            auto after = After(c);
            if (fault == 0) { ++after.purse; }
            if (fault == 1) { ++after.balance; }
            if (fault == 2) { ++after.source[0]; }
            if (fault == 3) { ++after.scene; }
            if (fault == 4) { ++after.character[0]; }
            if (fault == 5) { ++after.reserve; }
            uncertain.Observe(direction, after, true, fault == 6 ? 16002 : 2);
            assert(uncertain.Busy());
            uncertain.Observe(direction, After(c), true, 17000);
            const auto failed = uncertain.Execute(f::wire::Verb::inspect, inspect, true, false, 17001, invoked);
            assert(failed.flags & f::wire::unresolved);
            assert(invoked.calls == 1);
        }
        auto over = c; over.amount = over.expected.limit + 1; assert(!f::wire::Valid(f::wire::Verb::transfer, over));
        over = c; over.amount = 0; assert(!f::wire::Valid(f::wire::Verb::transfer, over));
        over = c; over.expected.source[1] = direction == 1 ? 8 : 42; assert(!f::wire::Valid(f::wire::Verb::transfer, over));
        over = c; over.expected.entered = over.expected.limit + 1; assert(!f::wire::Valid(f::wire::Verb::transfer, over));
        if (direction == 1) { over = c; over.expected.purse = INT32_MAX; assert(!f::wire::Valid(f::wire::Verb::transfer, over)); }
        else { over = c; over.expected.balance = INT32_MAX; assert(!f::wire::Valid(f::wire::Verb::transfer, over)); }
    }
    for (std::uint32_t direction : {1U, 2U}) {
        f::Controller opening; Fake calls; auto c = Command(direction);
        c.expected.quote = c.expected.limit = c.expected.entered = c.expected.accept = c.expected.cancel = c.expected.helper = 0;
        c.amount = 0; assert(f::wire::Valid(f::wire::Verb::open_quote, c));
        opening.Observe(direction, c.expected, true, 1);
        const auto submitted = opening.Execute(f::wire::Verb::open_quote, c, true, true, 1, calls);
        assert(Outcome(submitted) == O::submitted && opening.Busy() && calls.calls == 1);
        opening.Observe(direction, State(direction), true, 2);
        assert(!opening.Busy());
        const auto repeated = opening.Execute(f::wire::Verb::open_quote, c, true, true, 3, calls);
        assert(!std::memcmp(&submitted, &repeated, sizeof(submitted)) && calls.calls == 1);
        f::Controller changed; changed.Observe(direction, c.expected, true, 1);
        changed.Execute(f::wire::Verb::open_quote, c, true, true, 1, calls);
        auto wrong = State(direction); ++wrong.balance;
        changed.Observe(direction, wrong, true, 2);
        assert(changed.Busy() && !changed.NeedsObservation(direction));
    }
    f::Controller stale; auto c = Command(); stale.Observe(1, c.expected, true, 1);
    ++c.expected.balance; ++c.expected.limit;
    assert(Outcome(stale.Execute(f::wire::Verb::transfer, c, true, true, 2, invoker)) == O::stale);
    assert(!invoker.calls);
}
