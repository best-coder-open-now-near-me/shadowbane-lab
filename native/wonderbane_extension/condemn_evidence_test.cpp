#include "condemn_evidence.h"
#include <iostream>
namespace ko = wonderbane::extension::condemn;
namespace ev = ko::evidence;
namespace {
int failures = 0;
void Check(bool yes, const char* why) { if (!yes) { ++failures; std::cerr << why << '\n'; } }
constexpr ko::Cursor baseline{12, 34, 0, 2, 1};
constexpr ko::Key local{99, 53}, building{20, 8}, entry{30, 23};
struct Fixture {
    std::unique_ptr<ko::Batch> batch = std::make_unique<ko::Batch>();
    std::vector<ev::Proof> completed;
    ev::Window window{baseline, 7, local};
    Fixture() {
        batch->after = baseline; batch->after.sequence = 3; batch->count = 3;
        for (unsigned i = 0; i < 3; ++i) {
            auto& r = batch->records[i]; r.sequence = i + 1; r.decode_sequence = 1;
            r.stage = i + 1; r.flags = i ? 7 : 3; r.thread_id = i ? 8 : 6;
            r.tick_ms = 100 + i; r.scene_epoch = 7; r.local = local;
            r.caller_rva = i ? 0x1234 : 0x3625bc;
            r.payload.operation = 17; r.payload.fields = 1; r.payload.building = building;
            r.payload.entry = entry; r.payload.state = 1;
        }
    }
    bool Consume() { return window.Consume(*batch, completed); }
};
}
int main() {
    {
        Fixture f;
        Check(f.Consume() && f.completed.size() == 1 && f.completed[0].Enabled(building, entry), "keyed enable triple");
        Check(!f.completed[0].Enabled({21, 8}, entry) && !f.completed[0].Enabled(building, {31, 23}), "exact keys required");
        Check(!f.Consume() && !f.window.Healthy() && f.completed.empty(), "batch replay poisons interval");
        f.batch->count = 0;
        Check(!f.Consume(), "failed interval never rearms");
    }
    for (unsigned fault = 0; fault < 22; ++fault) {
        Fixture f; auto& b = *f.batch;
        switch (fault) {
        case 0: ++b.after.rejected; break;
        case 1: ++b.after.ticket_drops; break;
        case 2: ++b.after.process_id; break;
        case 3: ++b.after.creation; break;
        case 4: ++b.after.sequence; break;
        case 5: --b.records[1].sequence; break;
        case 6: b.records[1].flags = 3; break;
        case 7: ++b.records[0].caller_rva; break;
        case 8: ++b.records[1].scene_epoch; break;
        case 9: ++b.records[2].local[0]; break;
        case 10: b.records[2].tick_ms = 0; break;
        case 11: ++b.records[2].thread_id; break;
        case 12: ++b.records[2].caller_rva; break;
        case 13: ++b.records[2].payload.state; break;
        case 14: ++b.records[1].payload.entry[0]; break;
        case 15: b.records[2].decode_sequence = 2; break;
        case 16: b.records[1].stage = 3; break;
        case 17: b.records[0].payload.scope = 5; break;
        case 18: b.records[0].payload.guild = {1, 23}; break;
        case 19: b.records[0].payload.rows[511].flags = 1; break;
        case 20: b.records[0].payload.row_count = 513; break;
        case 21: b.records[0].payload.building = {1, 0}; break;
        }
        Check(!f.Consume() && !f.window.Healthy() && f.completed.empty(), "malformed evidence poisons interval");
    }
    for (unsigned state = 0; state < 5; ++state) {
        Fixture f;
        for (unsigned i = 0; i < 3; ++i) {
            auto& p = f.batch->records[i].payload;
            if (state == 0) { p.operation = 12; p.building = {}; }
            if (state == 1) { p.status = 1; }
            if (state == 2) { p.state = 0; }
            if (state == 3) { p.inverted = 1; }
            if (state == 4) { p.reported_count = 1; }
        }
        Check(f.Consume() && f.completed.size() == 1 && !f.completed[0].Enabled(building, entry),
            "list, rejection, disable, inversion and nonempty count are not enable proof");
    }
    {
        Fixture f;
        f.batch->count = 1; f.batch->after.sequence = 1;
        Check(f.Consume() && f.completed.empty(), "decode alone never completes");
        f.batch->records[0] = f.batch->records[1]; f.batch->after.sequence = 2;
        Check(f.Consume() && f.completed.empty(), "processing alone never completes");
        f.batch->records[0] = f.batch->records[2]; f.batch->after.sequence = 3;
        Check(f.Consume() && f.completed.size() == 1, "stages across drains retain lineage");
    }
    {
        Fixture f;
        // Two decodes interleave; process/return of the first then the second.
        f.batch->records[5] = f.batch->records[2]; f.batch->records[4] = f.batch->records[1];
        f.batch->records[3] = f.batch->records[2]; f.batch->records[2] = f.batch->records[1];
        f.batch->records[1] = f.batch->records[0];
        for (unsigned i = 0; i < 6; ++i) {
            auto& r = f.batch->records[i]; r.sequence = i + 1; r.tick_ms = 100 + i;
            r.decode_sequence = i == 1 || i >= 4 ? 2 : 1;
        }
        f.batch->count = 6; f.batch->after.sequence = 6;
        Check(f.Consume() && f.completed.size() == 2, "interleaved complete triples");
    }
    {
        Fixture f;
        f.batch->records[3] = f.batch->records[2]; f.batch->records[3].sequence = 4;
        f.batch->count = 4; f.batch->after.sequence = 4;
        Check(!f.Consume() && f.completed.empty(), "bad trailing lineage discards earlier completion in drain");
    }
    {
        Fixture f; auto old = baseline; old.sequence = 1;
        ev::Window w(old, 7, local);
        f.batch->records[0] = f.batch->records[1]; f.batch->records[1] = f.batch->records[2];
        f.batch->count = 2;
        Check(w.Consume(*f.batch, f.completed) && f.completed.empty(), "pre-baseline decode never proves new work");
        w.Invalidate(); Check(!w.Consume(*f.batch, f.completed), "read failure is sticky");
    }
    {
        Fixture f;
        for (unsigned offset = 0; offset < 64; offset += 32) {
            for (unsigned i = 0; i < 32; ++i) {
                auto& r = f.batch->records[i]; r = f.batch->records[0];
                r.sequence = offset + i + 1; r.decode_sequence = offset + i + 1;
                r.tick_ms = offset + i + 100;
            }
            f.batch->count = 32; f.batch->after.sequence = offset + 32;
            Check(f.Consume() && f.completed.empty(), "bounded pending decodes");
        }
        auto& r = f.batch->records[0]; r.sequence = 65; r.decode_sequence = 65; r.tick_ms = 165;
        f.batch->count = 1; f.batch->after.sequence = 65;
        Check(!f.Consume(), "lineage exhaustion fails without evicting proof");
    }
    Check(!ev::Window({}, 7, local).Healthy() && !ev::Window(baseline, 0, local).Healthy()
        && !ev::Window(baseline, 7, {99, 23}).Healthy(), "invalid process or scene cannot arm");
    return failures;
}
