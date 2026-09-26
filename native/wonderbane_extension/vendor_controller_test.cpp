#include "vendor_controller.h"
#include "vendor_command_queue.h"
#undef NDEBUG
#include <cassert>
#include <cstdio>
namespace v = wonderbane::extension::vendor;
namespace w = v::wire;
struct Fake final : v::Invoker {
    unsigned calls = 0;
    w::Outcome outcome = w::Outcome::submitted;
    w::Outcome Invoke(w::Verb, const w::Snapshot&, std::uint32_t) noexcept override { ++calls; return outcome; }
};
w::Snapshot Snapshot() {
    w::Snapshot s{};
    s.scene = 1; s.root = 100; s.manager = 200; s.menu = 300; s.recipe = 400;
    s.hireling = 500; s.building = 2229645; s.vendor = 2517204; s.item_template = 26990;
    s.prefix = s.suffix = 3362971591U; s.mode = 1; s.table = 12; s.quantity = 1;
    s.count = 2; s.slots[0].entry = 600; s.slots[1].entry = 700; return s;
}
w::Command Command(const v::Controller& controller, unsigned request = 1) {
    w::Command c{}; c.host = {1, 1, 1}; c.window = 1000;
    c.request[0] = static_cast<unsigned char>(request); c.expected = controller.Current(); return c;
}
bool Is(const w::Receipt& r, w::Outcome o) { return r.signature == w::magic && r.outcome == static_cast<unsigned>(o); }
int main(int argc, char**) {
    if (argc > 1) {
        auto s = Snapshot(); s.revision = 1;
        w::Command c{}; c.host = {1234, 7, 0x1122334455667788}; c.window = 0x76543210;
        for (std::size_t i = 0; i < c.request.size(); ++i) { c.request[i] = static_cast<unsigned char>(i + 1); }
        c.expected = s;
        w::Receipt r{}; r.request = c.request; r.host = c.host; r.window = c.window;
        r.snapshot = s; r.outcome = 1; r.flags = w::in_flight;
        auto print = [](const auto& object) {
            const auto* bytes = reinterpret_cast<const unsigned char*>(&object);
            for (std::size_t i = 0; i < sizeof(object); ++i) { std::printf("%02x", bytes[i]); }
            std::printf("\n");
        };
        print(s); print(c); print(r); return 0;
    }

    {
        v::Controller c; Fake f; c.Observe(Snapshot(), true, false); auto command = Command(c);
        assert(Is(c.Execute(w::Verb::create, command, false, true, f), w::Outcome::stale));
        assert(Is(c.Execute(w::Verb::create, command, true, false, f), w::Outcome::unavailable));
        auto wrong = command; ++wrong.expected.vendor;
        assert(Is(c.Execute(w::Verb::create, wrong, true, true, f), w::Outcome::stale));
        assert(!f.calls);
        auto receipt = c.Execute(w::Verb::create, command, true, true, f);
        assert(Is(receipt, w::Outcome::submitted) && (receipt.flags & w::in_flight) && f.calls == 1);
        assert(Is(c.Execute(w::Verb::create, command, true, true, f), w::Outcome::submitted) && f.calls == 1);
        wrong = command; ++wrong.expected.building;
        assert(Is(c.Execute(w::Verb::create, wrong, true, true, f), w::Outcome::invalid) && f.calls == 1);
        assert(Is(c.Execute(w::Verb::create, Command(c, 2), true, true, f), w::Outcome::pending));
        auto s = Snapshot(); s.slots[0] = {600, 123, 1}; c.Observe(s, true, false);
        auto inspect = Command(c, 3); inspect.expected = {};
        receipt = c.Execute(w::Verb::inspect, inspect, true, true, f);
        assert(receipt.transition_item == 123 && receipt.transition_request == command.request && (receipt.flags & w::ready));
        assert(Is(c.Execute(w::Verb::create, command, true, true, f), w::Outcome::submitted) && f.calls == 1);
        command = Command(c, 4); assert(Is(c.Execute(w::Verb::create, command, true, true, f), w::Outcome::submitted));
        s.slots[1] = {700, 124, 1}; c.Observe(s, true, false);
        assert(Is(c.Execute(w::Verb::create, Command(c, 5), true, true, f), w::Outcome::invalid) && f.calls == 2);
    }
    {
        v::Controller c; Fake f; c.Observe(Snapshot(), true, false);
        const auto command = Command(c);
        assert(Is(c.Execute(w::Verb::create, command, true, true, f), w::Outcome::submitted));
        auto s = Snapshot(); s.count = 4; s.slots[2].entry = 800; s.slots[3].entry = 900;
        c.Observe(s, true, false);
        auto probe = Command(c, 2); probe.expected = {};
        assert(c.Execute(w::Verb::inspect, probe, true, true, f).flags & w::in_flight);
        s.slots[0] = {600, 123, 1}; c.Observe(s, true, false);
        const auto r = c.Execute(w::Verb::inspect, probe, true, true, f);
        assert((r.flags & w::ready) && r.transition_item == 123 && r.snapshot.count == 4);
        assert(Is(c.Execute(w::Verb::create, Command(c, 3), true, true, f), w::Outcome::submitted));
    }

    for (bool burst : {false, true}) {
        v::Controller c; Fake f; auto s = Snapshot(); s.multiple = 1;
        c.Observe(s, true, false); const auto command = Command(c);
        assert(Is(c.Execute(w::Verb::create, command, true, true, f), w::Outcome::submitted));
        auto probe = Command(c, 9); probe.expected = {};
        if (!burst) {
            s.slots[0] = {600, 123, 1}; c.Observe(s, true, false);
            auto r = c.Execute(w::Verb::inspect, probe, true, true, f);
            assert((r.flags & w::in_flight) && !r.transition_item);
            assert(Is(c.Execute(w::Verb::create, Command(c, 2), true, true, f), w::Outcome::pending));
        }
        s.slots[0] = {600, 123, 1}; s.slots[1] = {700, 124, 1};
        s.recipe = 0; s.quantity = 0; s.multiple = 0;
        c.Observe(s, true, false);
        const auto r = c.Execute(w::Verb::inspect, probe, true, true, f);
        assert((r.flags & w::ready) && r.transition_request == command.request && r.transition_item == 124);
        assert(Is(c.Execute(w::Verb::create, command, true, true, f), w::Outcome::submitted));
        assert(f.calls == 1);
    }
    // Once observed, a partial arrival cannot disappear, even if another replaces it.
    for (int failure = 0; failure < 5; ++failure) {
        v::Controller c; Fake f; auto s = Snapshot(); s.multiple = 1;
        c.Observe(s, true, false);
        assert(Is(c.Execute(w::Verb::create, Command(c), true, true, f), w::Outcome::submitted));
        s.slots[0] = {600, 123, 1}; c.Observe(s, true, false);
        if (failure == 0) { s.slots[0] = {600, 125, 1}; }
        if (failure == 1) { s.count = 3; s.slots[1] = {700, 124, 1}; s.slots[2] = {800, 125, 1}; }
        if (failure == 2) { ++s.vendor; }
        if (failure == 3) { s.count = 1; s.slots[1] = {}; }
        c.Observe(s, failure != 4, false);
        auto probe = Command(c, 9); probe.expected = {};
        assert(c.Execute(w::Verb::inspect, probe, true, true, f).flags & w::unresolved);
        assert(f.calls == 1);
    }
    // Occupied slots are excluded; newly unlocked slots do not change a pending request's size.
    {
        v::Controller c; Fake f; auto s = Snapshot(); s.multiple = 1;
        s.slots[0] = {600, 100, 2}; c.Observe(s, true, false);
        const auto command = Command(c);
        assert(Is(c.Execute(w::Verb::create, command, true, true, f), w::Outcome::submitted));
        s.count = 3; s.slots[2] = {800, 0, 0}; c.Observe(s, true, false);
        s.slots[1] = {700, 123, 1}; c.Observe(s, true, false);
        auto probe = Command(c, 9); probe.expected = {};
        const auto r = c.Execute(w::Verb::inspect, probe, true, true, f);
        assert((r.flags & w::ready) && r.transition_request == command.request);
        assert(Is(c.Execute(w::Verb::create, Command(c, 2), true, true, f), w::Outcome::submitted));
        assert(f.calls == 2);
    }
    for (int failure = 0; failure < 4; ++failure) {
        v::Controller c; Fake f; c.Observe(Snapshot(), true, false);
        assert(Is(c.Execute(w::Verb::create, Command(c), true, true, f), w::Outcome::submitted));
        auto s = Snapshot();
        if (failure == 0) { s.scene = 2; }
        if (failure == 1) { s.slots[0] = {600, 123, 1}; s.slots[1] = {700, 124, 1}; }
        if (failure == 3) { s.count = 1; s.slots[1] = {}; }
        c.Observe(s, failure != 2, false);
        assert(Is(c.Execute(w::Verb::create, Command(c, 2), true, true, f),
            failure == 2 ? w::Outcome::invalid : w::Outcome::uncertain));
        assert(f.calls == 1);
    }
    {
        v::Controller c; Fake f; auto s = Snapshot(); s.slots[0] = {600, 123, 2};
        c.Observe(s, true, false); auto cmd = Command(c); cmd.item = 123;
        assert(Is(c.Execute(w::Verb::keep, cmd, true, true, f), w::Outcome::submitted));
        s.slots[0] = {800, 0, 0}; c.Observe(s, true, false);
        auto probe = Command(c, 2); probe.expected = {};
        assert(c.Execute(w::Verb::inspect, probe, true, true, f).flags & w::in_flight);
        c.Observe(s, true, true);
        const auto r = c.Execute(w::Verb::inspect, probe, true, true, f);
        assert(r.transition_item == 123 && r.transition_request == cmd.request && (r.flags & w::ready));
        assert(Is(c.Execute(w::Verb::keep, cmd, true, true, f), w::Outcome::submitted) && f.calls == 1);
    }
    for (auto outcome : {w::Outcome::stale, w::Outcome::uncertain}) {
        v::Controller c; Fake f; f.outcome = outcome; c.Observe(Snapshot(), true, false);
        assert(Is(c.Execute(w::Verb::create, Command(c), true, true, f), outcome));
        f.outcome = w::Outcome::submitted;
        assert(Is(c.Execute(w::Verb::create, Command(c, 2), true, true, f),
            outcome == w::Outcome::stale ? w::Outcome::submitted : w::Outcome::uncertain));
    }
    {
        auto cmd = std::make_shared<v::QueuedCommand>();
        assert(v::Queue(cmd)); assert(!v::Queue(cmd)); assert(v::Take() == cmd); assert(!v::Take());
        w::Receipt r{}; v::Complete(cmd, r); assert(cmd->state.load() == 2);
        v::Release(cmd); assert(v::Queue(cmd)); v::Release(cmd);
    }
    {
        auto s = Snapshot(); s.revision = 1;
        assert(w::ValidSnapshot(s));
        s.slots[1].entry = s.slots[0].entry; assert(!w::ValidSnapshot(s));
        s = Snapshot(); s.revision = 1; s.slots[0].state = 1; assert(!w::ValidSnapshot(s));
        s = Snapshot(); s.revision = 1; s.count = 17; assert(!w::ValidSnapshot(s));
        s = Snapshot(); s.revision = 1; s.quantity = 2; assert(!w::RandomScepter(s));
        s.multiple = 1; assert(!w::RandomScepter(s));
        s.quantity = 1; assert(w::RandomScepter(s));
        s.multiple = 2; assert(!w::RandomScepter(s));
    }
    // Additive capability inspection changes neither the payload ABI nor legacy recipe admission.
    {
        static_assert(static_cast<unsigned>(w::Verb::create_random)==32 && static_cast<unsigned>(w::Verb::inspect_random)==33);
        static_assert(sizeof(w::Command)==576 && sizeof(w::Receipt)==384);
        v::Controller c; Fake f; auto s=Snapshot(); s.item_template=5051080; s.table=16;
        c.Observe(s,true,false,100); auto cmd=Command(c); assert(w::Valid(w::Verb::create_random,cmd));
        assert(!w::Valid(w::Verb::create,cmd));
        auto probe=Command(c,9); probe.expected={};
        assert(w::Valid(w::Verb::inspect_random,probe));
        assert(Is(c.Execute(w::Verb::inspect_random,probe,true,true,f,100),w::Outcome::observed) && !f.calls);
        auto original=c.Execute(w::Verb::create_random,cmd,true,true,f,100);
        assert(Is(original,w::Outcome::submitted) && c.Busy() && f.calls==1);
        assert(Is(c.Execute(w::Verb::create_random,cmd,true,true,f,101),w::Outcome::submitted) && f.calls==1);
        auto keep=Command(c,2); keep.item=333;
        assert(Is(c.Execute(w::Verb::keep,keep,true,true,f,101),w::Outcome::pending));
        s.slots[0]={600,333,1}; c.Observe(s,true,false,102);
        auto observed=c.Execute(w::Verb::inspect_random,probe,true,true,f,102);
        assert(!c.Busy() && observed.transition_request==cmd.request && observed.transition_item==333 && (observed.flags&w::ready));
        assert(Is(c.Execute(w::Verb::create_random,cmd,true,true,f,103),w::Outcome::submitted) && f.calls==1);
        cmd.item=1; assert(!w::Valid(w::Verb::create_random,cmd));
        cmd.item=0; cmd.expected.multiple=1; assert(!w::Valid(w::Verb::create_random,cmd));
        cmd.expected.multiple=0; cmd.expected.table=0; assert(!w::Valid(w::Verb::create_random,cmd));
        cmd.expected.table=16; cmd.expected.item_template=0; assert(!w::Valid(w::Verb::create_random,cmd));
        cmd.expected.item_template=5051080; cmd.expected.quantity=2; assert(!w::Valid(w::Verb::create_random,cmd));
        cmd.expected.quantity=1; cmd.expected.mode=0; assert(!w::Valid(w::Verb::create_random,cmd));
        cmd.expected.mode=1; cmd.expected.prefix=1; assert(!w::Valid(w::Verb::create_random,cmd));
        cmd.expected.prefix=3362971591U; cmd.reserved[0]=1; assert(!w::Valid(w::Verb::create_random,cmd));
        probe.reserved[0]=1; assert(!w::Valid(w::Verb::inspect_random,probe));
    }
    // Native UI rejection/no addition is bounded uncertainty. Late additions cannot reopen spending.
    for(bool excess:{false,true}) {
        v::Controller c; Fake f; auto s=Snapshot(); s.item_template=25860; s.table=19;
        c.Observe(s,true,false,100); const auto cmd=Command(c);
        assert(Is(c.Execute(w::Verb::create_random,cmd,true,true,f,100),w::Outcome::submitted));
        if(excess) { s.slots[0]={600,333,1}; s.slots[1]={700,334,1}; }
        c.Observe(s,true,false,excess?101:5101);
        auto probe=Command(c,9); probe.expected={};
        assert(c.Execute(w::Verb::inspect_random,probe,true,true,f,5102).flags&w::unresolved);
        s.slots[0]={600,333,1}; s.slots[1]={700,0,0}; c.Observe(s,true,false,5103);
        assert(c.Busy() && f.calls==1);
        assert(Is(c.Execute(w::Verb::create_random,cmd,true,true,f,5103),w::Outcome::submitted) && f.calls==1);
    }
    {
        v::Controller c; Fake f; auto s=Snapshot(); s.item_template=5051080; s.table=16;
        c.Observe(s,true,false,1);
        assert(Is(c.Execute(w::Verb::create_random,Command(c),true,true,f,UINT64_MAX-4999),w::Outcome::exhausted) && !f.calls);
    }

}
