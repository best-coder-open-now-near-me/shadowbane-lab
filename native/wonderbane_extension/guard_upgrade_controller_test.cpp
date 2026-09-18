#include "guard_upgrade_controller.h"
#undef NDEBUG
#include <cassert>
#include <cstdio>
namespace g = wonderbane::extension::guard_upgrade;
namespace w = g::wire;
struct Fake final : g::Invoker {
    unsigned calls = 0, reopens = 0; w::Outcome result = w::Outcome::submitted;
    w::Outcome reopen_result = w::Outcome::submitted;
    w::Outcome Upgrade(const w::Snapshot&) noexcept override { ++calls; return result; }
    w::Outcome Reopen(const w::Snapshot&, const g::ReturnSnapshot&) noexcept override {
        ++reopens; return reopen_result;
    }
};
w::Snapshot State() {
    w::Snapshot s{}; auto& n = s.navigation;
    n.scene = n.revision = 1; n.root = 100; n.manager = 200; n.mode = 6;
    n.building_hud = 300; n.vendor_hud = 400; n.selected_entry = 500; n.visible = 3;
    n.building = {123, 8}; n.vendor = {777, 37}; n.initialized = 1; n.capacity = n.occupied = 1;
    s.rank = 1; s.cost = 100; s.funds = 150; s.can_upgrade = 1; s.control_flags = 3;
    s.upgrade_control = 600; s.progress_control = 700; return s;
}
w::Command Request(g::Controller& controller, unsigned id = 1) {
    w::Command c{}; c.host = {1, 1, 1}; c.window = 1000; c.request[0] = static_cast<unsigned char>(id);
    c.expected = controller.Current(); return c;
}
bool Is(const w::Receipt& r, w::Outcome o) { return r.outcome == static_cast<unsigned>(o); }
int main(int argc, char**) {
    g::Controller c; Fake fake; auto state = State(); c.Observe(state, true, 1); auto request = Request(c);
    if (argc > 1) {
        auto print = [](const auto& object) {
            for (auto* p = reinterpret_cast<const unsigned char*>(&object);
                p != reinterpret_cast<const unsigned char*>(&object) + sizeof(object); ++p) { std::printf("%02x", *p); }
            std::printf("\n");
        };
        print(request.expected); print(request);
        print(c.Execute(w::Verb::upgrade, request, true, true, 1, fake)); return 0;
    }
    for (int test = 0; test < 7; ++test) {
        auto bad = request;
        if (test == 0) { bad.expected.upgrading = 1; }
        if (test == 1) { bad.expected.funds = 99; }
        if (test == 2) { bad.expected.cost = 0; }
        if (test == 3) { bad.expected.can_upgrade = 0; }
        if (test == 4) { bad.expected.control_flags = 7; }
        if (test == 5) { bad.expected.navigation.vendor[1] = 42; }
        if (test == 6) { bad.expected.upgrade_control = bad.expected.progress_control; }
        assert(!w::Valid(w::Verb::upgrade, bad));
        assert(Is(c.Execute(w::Verb::upgrade, bad, true, true, 1, fake), w::Outcome::invalid));
    }
    assert(!fake.calls);
    assert(Is(c.Execute(w::Verb::upgrade, request, false, true, 1, fake), w::Outcome::stale));
    assert(Is(c.Execute(w::Verb::upgrade, request, true, false, 1, fake), w::Outcome::unavailable));
    auto stale = request; ++stale.expected.cost;
    assert(Is(c.Execute(w::Verb::upgrade, stale, true, true, 1, fake), w::Outcome::stale));
    assert(Is(c.Execute(w::Verb::upgrade, request, true, true, 1, fake), w::Outcome::submitted));
    assert(fake.calls == 1 && c.Busy());
    state.upgrading = 1; state.control_flags = 7; c.Observe(state, true, 2); assert(c.Busy());
    state.funds = 50; c.Observe(state, true, 3); assert(!c.Busy());
    assert(Is(c.Execute(w::Verb::upgrade, request, true, true, 4, fake), w::Outcome::submitted));
    assert(fake.calls == 1);
    assert(Is(c.Execute(w::Verb::upgrade, stale, true, true, 4, fake), w::Outcome::invalid));
    for (int failure = 0; failure < 7; ++failure) {
        g::Controller stopped; Fake invoke; auto before = State(); stopped.Observe(before, true, 1);
        auto command = Request(stopped);
        if (failure == 6) { invoke.result = w::Outcome::uncertain; }
        stopped.Execute(w::Verb::upgrade, command, true, true, 1, invoke);
        auto after = before; after.funds -= before.cost; after.upgrading = 1; after.control_flags = 7;
        if (failure == 0) { ++after.navigation.scene; }
        if (failure == 1) { ++after.navigation.building[0]; }
        if (failure == 2) { ++after.navigation.vendor[0]; }
        if (failure == 3) { --after.funds; }
        if (failure == 4) { after.rank += 2; }
        stopped.Observe(after, failure != 5, failure == 5 ? 15002 : 2);
        assert(stopped.Busy());
        after = before; after.funds -= before.cost; after.upgrading = 1; after.control_flags = 7;
        stopped.Observe(after, true, 15003); assert(stopped.Busy()); // No late uncertainty clearing.
        auto next = command; next.request[0] = 2;
        assert(Is(stopped.Execute(w::Verb::upgrade, next, true, true, 15003, invoke), w::Outcome::pending));
        assert(invoke.calls == 1);
    }
    g::Controller fast; Fake invoke; fast.Observe(State(), true, 1);
    fast.Execute(w::Verb::upgrade, Request(fast), true, true, 1, invoke);
    state = State(); state.funds = 50; ++state.rank;
    fast.Observe(state, true, 2); assert(!fast.Busy()); // Instant completion also requires debit.
    g::Controller interrupted; interrupted.Observe(State(), true, 1);
    interrupted.Execute(w::Verb::upgrade, Request(interrupted), true, true, 1, invoke);
    interrupted.Observe({}, false, 2); assert(interrupted.Busy());
    interrupted.Observe(state, true, 3); assert(!interrupted.Busy()); // Brief read gap.

    // Full observed sequence: idle post-deposit guard, server replacement roster,
    // one correlated reopen, fresh guard controls, exact debit plus progress.
    for (int failure = -1; failure < 12; ++failure) {
        g::Controller full; Fake f; auto before = State(); before.navigation.mode = 0;
        full.Observe(before, true, 1); auto spend = Request(full);
        full.Execute(w::Verb::upgrade, spend, true, true, 1, f);
        full.Observe({}, false, 2);
        g::ReturnSnapshot response{}; response.navigation = before.navigation;
        auto& n = response.navigation;
        n.mode = 6; n.visible = 1; n.vendor_hud = n.selected_entry = 0; n.vendor = {};
        n.building_hud = n.front_hud = 301;
        response.guard = before.navigation.vendor; response.rank = before.rank; response.funds = 50;
        auto rejected = response;
        if (failure == 0) { ++rejected.navigation.scene; }
        if (failure == 1) { ++rejected.navigation.building[0]; }
        if (failure == 2) { ++rejected.guard[0]; }
        if (failure == 3) { --rejected.funds; }
        if (failure == 4) { rejected.funds = before.funds; }
        if (failure == 5) { rejected.navigation.front_hud = 999; }
        if (failure == 6) { rejected.navigation.mode = 13; }
        if (failure == 7) { rejected.rank += 2; }
        full.ObserveReturn(rejected, true);
        w::Command inspect{}; inspect.host = spend.host; inspect.window = spend.window;
        inspect.request[0] = 2;
        if (failure == 8) { ++inspect.host.generation; }
        if (failure == 9) { f.reopen_result = w::Outcome::uncertain; }
        const auto reply = full.Execute(w::Verb::inspect, inspect, failure != 10, false, 3, f);
        assert(full.Busy() && f.calls == 1); // A debit never clears the spend by itself.
        if ((failure >= 0 && failure <= 8) || failure == 10) {
            assert(!f.reopens);
        } else {
            assert(f.reopens == 1);
            assert(bool(reply.flags & w::reopened) == (failure != 9));
        }
        full.ObserveReturn(response, true);
        full.Execute(w::Verb::inspect, inspect, true, false, 4, f);
        if (failure == -1 || failure == 9 || failure == 11) { assert(f.reopens == 1); }
        auto after = before;
        after.navigation.building_hud = 301; after.navigation.vendor_hud = 401;
        after.navigation.selected_entry = 501; after.navigation.front_hud = 401;
        after.upgrade_control = 601; after.progress_control = 701;
        after.funds = 50; after.upgrading = 1; after.control_flags = 7;
        if (failure == 11) { ++after.navigation.building_hud; }
        if ((failure >= 0 && failure <= 8) || failure == 10) {
            full.Observe({}, false, 15002); // Timed-out/wrong-owner request stays blocked.
        }
        full.Observe(after, true, (failure == -1 || failure == 11) ? 5 : 15003);
        assert(full.Busy() == (failure != -1));
        const auto final = full.Execute(w::Verb::inspect, inspect, true, true, 15004, f);
        if (failure == -1) {
            assert(final.flags & w::reopened);
            assert(!(final.flags & (w::in_flight | w::unresolved)));
        }
        full.Execute(w::Verb::upgrade, spend, true, true, 15005, f);
        assert(f.calls == 1); // Original upgrade never replays.
    }

    // A dropped page response can repeat only the observation request. The
    // original upgrade remains single-shot, with a fixed deadline and ownership.
    for (int scenario = 0; scenario < 13; ++scenario) {
        g::Controller retry; Fake f; auto before = State();
        retry.Observe(before, true, 1); const auto spend = Request(retry);
        retry.Execute(w::Verb::upgrade, spend, true, true, 1, f);
        retry.Observe({}, false, 2);
        g::ReturnSnapshot response{}; response.navigation = before.navigation;
        auto& n = response.navigation;
        n.visible = 1; n.vendor_hud = n.selected_entry = 0; n.vendor = {};
        n.building_hud = n.front_hud = 301;
        response.guard = before.navigation.vendor; response.rank = 1; response.funds = 50;
        w::Command inspect{}; inspect.host = spend.host; inspect.window = spend.window;
        inspect.request[0] = 2;
        retry.ObserveReturn(response, true);
        retry.Execute(w::Verb::inspect, inspect, true, false, 3, f);
        assert(f.reopens == 1 && f.calls == 1);
        retry.Observe({}, false, 4); retry.ObserveReturn(response, true);
        retry.Execute(w::Verb::inspect, inspect, true, false, 2002, f);
        assert(f.reopens == 1); // No rapid loop during the response wait.
        auto candidate = response; auto producer = inspect;
        if (scenario == 1) { ++candidate.navigation.building_hud; ++candidate.navigation.front_hud; }
        if (scenario == 2) { --candidate.funds; }
        if (scenario == 3) { ++candidate.guard[0]; }
        if (scenario == 4) { ++producer.host.generation; }
        if (scenario == 5) { ++producer.window; }
        if (scenario == 6) { candidate.navigation.front_hud = 999; }
        if (scenario == 7) { candidate.rank += 2; }
        if (scenario == 8) { f.reopen_result = w::Outcome::uncertain; }
        if (scenario == 9) { candidate.navigation.scene++; }
        if (scenario == 12) { candidate.navigation.building[0]++; }
        retry.ObserveReturn(candidate, true);
        retry.Execute(w::Verb::inspect, producer, scenario != 10, false, 2003, f);
        const bool retried = scenario == 0 || scenario == 8 || scenario == 11;
        assert(f.reopens == (retried ? 2U : 1U) && f.calls == 1);
        auto after = before;
        after.navigation.building_hud = 301; after.navigation.vendor_hud = 401;
        after.navigation.front_hud = 401; after.navigation.selected_entry = 501;
        after.upgrade_control = 601; after.progress_control = 701;
        after.funds = 50; after.upgrading = 1; after.control_flags = 7;
        if (scenario == 0) {
            retry.Observe(after, true, 2004); assert(!retry.Busy());
            retry.ObserveReturn(response, true);
            retry.Execute(w::Verb::inspect, inspect, true, true, 5000, f);
            assert(f.reopens == 2); // Confirmation ends all page requests.
        } else if (scenario == 8) {
            retry.ObserveReturn(response, true);
            retry.Execute(w::Verb::inspect, inspect, true, false, 4003, f);
            assert(f.reopens == 2); // Uncertain callback cannot be repeated.
            retry.Observe(after, true, 4004); assert(retry.Busy());
        } else if (scenario == 11) {
            retry.ObserveReturn(response, true);
            retry.Execute(w::Verb::inspect, inspect, true, false, 4003, f);
            assert(f.reopens == 3 && !retry.PendingReturn());
            retry.ObserveReturn(response, true);
            retry.Execute(w::Verb::inspect, inspect, true, false, 6003, f);
            assert(f.reopens == 3); // Exhaustion waits; never extends the deadline.
            retry.Observe({}, false, 15002);
            retry.Observe(after, true, 15003); assert(retry.Busy());
        } else {
            retry.Observe({}, false, 15002);
            retry.ObserveReturn(response, true);
            retry.Execute(w::Verb::inspect, inspect, true, false, 15003, f);
            assert(f.reopens == 1 && retry.Busy());
        }
        retry.Execute(w::Verb::upgrade, spend, true, true, 15004, f);
        assert(f.calls == 1); // Repeated original request never spends again.
    }
}
