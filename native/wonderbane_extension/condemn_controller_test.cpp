#include "condemn_controller.h"
#include <iostream>
namespace ko = wonderbane::extension::condemn;
namespace w = ko::wire;
namespace n = ko::native;
namespace {
int failures = 0;
void Check(bool v, const char* why) { if (!v) { ++failures; std::cerr << why << '\n'; } }
struct Calls final : ko::Invoker {
    ko::Cursor cursor{12, 34, 0, 2, 1};
    unsigned opens = 0, adds = 0, enables = 0, reads = 0;
    bool readable = true, drift = false;
    n::Result result = n::Result::submitted;
    bool Baseline(ko::Cursor& out) noexcept override {
        ++reads; out = cursor; if (drift && reads == 2) { ++out.sequence; } return readable;
    }
    n::Result Invoke(n::Action a, const n::Target&, const n::Snapshot&) noexcept override {
        if (a == n::Action::open) { ++opens; }
        else if (a == n::Action::add) { ++adds; }
        else { ++enables; }
        return result;
    }
};
struct Fixture {
    ko::Controller controller;
    Calls calls;
    n::Snapshot s{};
    w::Command command{}, inspect{};
    std::unique_ptr<ko::Batch> batch = std::make_unique<ko::Batch>();
    std::uint64_t now = 100;
    Fixture() {
        s.scene = 7; s.local = {99, 53}; s.root = 100; s.manager = 200;
        s.building_hud = 300; s.open_button = 400; s.front = 300; s.building = {20, 8};
        command.host = {10, 1, 456}; command.window = 123; command.request[0] = 1;
        command.target = {{20, 8}, {30, 23}, 5};
        inspect = command; inspect.request[0] = 2; inspect.transition_request = command.request;
        batch->after = calls.cursor;
    }
    void List(bool row = false, bool enabled = false) {
        s.kos = 500; s.list = 600; s.front = 500; s.context = s.building;
        s.entry = row ? 700 : 0; s.row = row ? 800 : 0; s.entry_key = row ? n::Key{30, 23} : n::Key{};
        s.count = row ? 1 : 0; s.enabled = enabled ? 1 : 0;
    }
    void Observe(bool valid = true) { controller.Observe(command.target, s, valid, batch.get(), now); }
    w::Receipt Start() {
        controller.Observe(command.target, s, true, nullptr, now);
        const auto seen = controller.Execute(w::Verb::inspect, inspect, true, true, now, calls);
        command.expected = seen.snapshot;
        return controller.Execute(w::Verb::ensure, command, true, true, now, calls);
    }
    w::Receipt Poll(bool live = true, bool ready = true) {
        return controller.Execute(w::Verb::inspect, inspect, live, ready, now, calls);
    }
    void Response(unsigned op = 17, bool enabled = true) {
        batch->count = 3; batch->after.sequence = calls.cursor.sequence + 3;
        for (unsigned i = 0; i < 3; ++i) {
            auto& r = batch->records[i]; r = {}; r.sequence = static_cast<LONG64>(calls.cursor.sequence + i + 1);
            r.decode_sequence = calls.cursor.sequence + 1; r.stage = i + 1; r.flags = i ? 7 : 3;
            r.thread_id = i ? 8 : 6; r.tick_ms = now; r.scene_epoch = s.scene; r.local = s.local;
            r.caller_rva = i ? 0x1234 : 0x3625bc; r.payload.operation = op; r.payload.fields = 1;
            r.payload.building = op == 17 ? s.building : n::Key{}; r.payload.entry = s.entry_key;
            r.payload.state = enabled ? 1 : 0;
        }
        calls.cursor = batch->after;
    }
    void Empty() { batch->count = 0; batch->after = calls.cursor; }
};
}
int main() {
    {
        Fixture f; auto r = f.Start();
        Check(r.outcome == static_cast<unsigned>(w::Outcome::submitted) && f.calls.opens == 1, "opens once");
        f.now++; f.Observe(); f.Poll(); Check(f.calls.opens == 1, "opening is never replayed");
        f.List(); f.now++; f.Observe(); f.Poll(); Check(f.calls.adds == 1 && f.controller.Busy(), "missing crest adds under same owner");
        f.Response(12, false); f.now++; f.Observe(); f.Poll();
        Check(f.calls.adds == 1 && !f.calls.enables && f.controller.Busy(), "unkeyed list neither completes nor retries add");
        f.Empty(); f.List(true); f.now++; f.Observe(); f.Poll();
        Check(f.calls.enables == 1 && f.controller.Busy(), "fresh scoped disabled row enables once");
        f.now++; f.Response(); f.Observe();
        Check(f.controller.Busy(), "reply without enabled row does not complete");
        f.Empty(); f.List(true, true); f.now++; f.Observe(); r = f.Poll();
        Check(!f.controller.Busy() && r.phase == static_cast<unsigned>(w::Phase::verified)
            && r.completion_sequence == 6, "keyed reply plus later owned scoped row completes composite");
        r = f.controller.Execute(w::Verb::ensure, f.command, true, true, f.now, f.calls);
        Check(r.outcome == static_cast<unsigned>(w::Outcome::submitted) && f.calls.opens == 1
            && f.calls.adds == 1 && f.calls.enables == 1, "duplicate original returns immutable submission");
        ++f.command.target.scope;
        Check(f.controller.Execute(w::Verb::ensure, f.command, true, true, f.now, f.calls).outcome
            == static_cast<unsigned>(w::Outcome::invalid), "same UUID cannot change payload");
    }
    for (unsigned which = 0; which < 4; ++which) {
        Fixture f; f.Start(); f.List(); f.now++; f.Observe();
        if (which == 0) { ++f.inspect.host.generation; }
        if (which == 1) { ++f.inspect.window; }
        if (which == 2) { ++f.inspect.transition_request[0]; }
        if (which == 3) { f.inspect.target.scope = 4; }
        f.Poll(); Check(!f.calls.adds && f.controller.Busy(), "other producer, window, transition or scope cannot advance");
    }
    {
        Fixture f; f.Start(); f.List(); f.now++; f.Observe();
        f.Poll(false); f.Poll(true, false); Check(!f.calls.adds, "lost lease or foreground cannot advance");
        f.Poll(); Check(f.calls.adds == 1, "original live producer advances");
    }
    for (unsigned fault = 0; fault < 8; ++fault) {
        Fixture f; f.List(true); f.Start(); f.now++;
        if (fault == 0) { ++f.s.scene; }
        if (fault == 1) { ++f.s.context[0]; }
        if (fault == 2) { ++f.s.entry_key[0]; }
        if (fault == 3) { ++f.batch->after.rejected; }
        if (fault == 4) { f.now = 0; }
        if (fault == 5) { f.now = 45101; }
        if (fault == 6) { f.Response(17, false); }
        if (fault == 7) { f.Response(); ++f.batch->records[2].thread_id; }
        f.Observe(); const auto r = f.Poll();
        Check((r.flags & w::unresolved) && f.controller.Busy() && f.calls.enables == 1, "uncertainty retains ownership without retry");
    }
    {
        Fixture f; f.List(true); f.Start(); f.now++;
        f.controller.Observe(f.command.target, f.s, true, nullptr, f.now);
        Check(f.Poll().flags & w::unresolved, "recorder read failure holds barrier");
    }
    {
        Fixture f; f.List(true, true); auto r = f.Start();
        Check(!f.controller.Busy() && r.phase == static_cast<unsigned>(w::Phase::existing)
            && !f.calls.enables && !r.completion_sequence, "existing enabled row is read-only, not new action proof");
    }
    {
        Fixture f; f.Start(); f.List(true, true); f.now++; f.Observe(); auto r = f.Poll();
        Check(!f.controller.Busy() && r.phase == static_cast<unsigned>(w::Phase::existing)
            && !f.calls.enables, "opening an existing enabled list requires no toggle");
    }
    {
        Fixture f; f.List(); f.Start(); f.List(true, true); f.now++; f.Observe();
        Check((f.Poll().flags & w::unresolved) && !f.calls.enables, "enabled row appearing during add cannot falsely finish");
    }
    for (bool uncertain : {false, true}) {
        Fixture f; f.calls.result = uncertain ? n::Result::uncertain : n::Result::unavailable;
        auto r = f.Start();
        Check(f.controller.Busy() == uncertain && ((r.flags & w::unresolved) != 0) == uncertain,
            "initial uninvoked failure differs from uncertain callback");
        f.controller.Execute(w::Verb::ensure, f.command, true, true, f.now, f.calls);
        Check(f.calls.opens == 1, "even unavailable original is not replayed");
    }
    {
        Fixture f; f.Start(); f.List(); f.now++; f.Observe(); f.calls.result = n::Result::unavailable;
        Check((f.Poll().flags & w::unresolved) && f.controller.Busy(), "later unavailable action keeps prior effects unresolved");
    }
    {
        Fixture f; f.calls.drift = true; auto r = f.Start();
        Check(!f.calls.opens && r.outcome == static_cast<unsigned>(w::Outcome::pending), "undrained response defers first invocation");
        f.now++; f.Observe(); f.Poll(); Check(f.calls.opens == 1, "deferred initial open eventually invokes once");
    }
    {
        Fixture f; f.List(true); f.Start(); f.Response(); f.List(true, true); f.now++;
        // A reply from another tower cannot confirm even when the UI changed.
        for (unsigned i = 0; i < 3; ++i) { ++f.batch->records[i].payload.building[0]; }
        f.Observe(); Check(f.controller.Busy(), "wrong tower reply cannot complete");
    }
    {
        Fixture f; f.command.expected = w::Encode(f.s, 1);
        Check(w::Valid(w::Verb::ensure, f.command), "explicit packed wire accepts scoped owner");
        f.command.reserved[0] = 1; Check(!w::Valid(w::Verb::ensure, f.command), "wire rejects extension bytes");
        f.command.reserved[0] = 0; f.command.target.scope = 3;
        Check(!w::Valid(w::Verb::ensure, f.command), "wire excludes character and mixed scope");
    }
    return failures;
}
