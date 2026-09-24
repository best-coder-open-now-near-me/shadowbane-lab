#include "furnishing_queue.h"
#undef NDEBUG
#include <cassert>
#include <cstring>
#include <map>
#include <memory>
#include <vector>

namespace f = wonderbane::extension::furnishing;
using Q = f::QueueReceipt;
using A = Q::Address;
namespace {
constexpr A queue = 0x100000, head = 0x110000, pool = 0x200000, type = 0x1549d38;
constexpr A render = 0x300000, render2 = 0x310000, other = 0x320000;
constexpr A node0 = 0x400000, node1 = 0x410000, node2 = 0x420000;
struct Memory {
    std::map<A, unsigned char> bytes;
    std::map<A, A> nodes;
    std::map<A, unsigned> reads;
    bool admitted = true, fail_erase = false, fail_after_erase = false;
    bool invalidate_erase = false, damage_erase = false, reenter_erase = false;
    A changed_read = 0; unsigned changed_read_number = 2;
    unsigned erases = 0;
    Q* receipt = nullptr;
    template<class T> void Put(A at, T value) {
        const auto* data = reinterpret_cast<const unsigned char*>(&value);
        for (std::size_t i = 0; i < sizeof(T); ++i) { bytes[at + static_cast<A>(i)] = data[i]; }
    }
    void Wrapper(A at, A object) {
        for (A i = 0; i < 32; i += 4) { Put(at + i, A{}); }
        Put(at, type); Put(at + 0x1c, object);
    }
    A Build(const std::vector<A>& keys, std::size_t lo, std::size_t hi,
            A parent, unsigned depth, unsigned deepest) {
        if (lo == hi) { return 0; }
        const auto middle = lo + (hi - lo) / 2; const auto p = keys[middle];
        const auto left = Build(keys, lo, middle, p, depth + 1, deepest);
        const auto right = Build(keys, middle + 1, hi, p, depth + 1, deepest);
        Put(p, depth && depth == deepest ? A{0} : A{1}); Put(p + 4, parent);
        Put(p + 8, left); Put(p + 12, right); Put(p + 16, nodes[p]); return p;
    }
    void Tree() {
        std::vector<A> keys; for (const auto& entry : nodes) { keys.push_back(entry.first); }
        unsigned deepest = 0; for (auto n = keys.size(); n > 1; n /= 2) { ++deepest; }
        const auto root = Build(keys, 0, keys.size(), head, 0, deepest);
        Put(queue, head); Put(queue + 4, static_cast<A>(keys.size()));
        Put(head + 4, root); Put(head + 8, keys.empty() ? head : keys.front());
        Put(head + 12, keys.empty() ? head : keys.back());
    }
    static bool Read(void* context, A at, void* out, std::size_t size) noexcept {
        auto& m = *static_cast<Memory*>(context);
        const auto number = ++m.reads[at];
        auto* dest = static_cast<unsigned char*>(out);
        for (std::size_t i = 0; i < size; ++i) {
            const auto found = m.bytes.find(at + static_cast<A>(i));
            if (found == m.bytes.end()) { return false; }
            dest[i] = found->second;
        }
        if (at == m.changed_read && number == m.changed_read_number) { dest[0] ^= 4; }
        return true;
    }
    static bool Admit(void* context) noexcept { return static_cast<Memory*>(context)->admitted; }
    static bool Erase(void* context, A q, A node) noexcept {
        auto& m = *static_cast<Memory*>(context); ++m.erases;
        assert(q == queue && m.nodes.contains(node));
        assert(m.receipt && !m.receipt->ReleaseAllowed());
        if (m.reenter_erase) {
            assert(!m.receipt->Retire(7));
            assert(!m.receipt->Prepare(queue, {pool, 16, 1}, &render, 1, 8));
        }
        if (m.fail_erase) { return false; }
        m.nodes.erase(node); m.Tree();
        if (m.invalidate_erase) { m.admitted = false; }
        if (m.damage_erase && !m.nodes.empty()) { m.Put(m.nodes.begin()->first + 16, other); }
        return !m.fail_after_erase;
    }
    std::unique_ptr<Q> Make() {
        auto q = std::make_unique<Q>(Q::Access{this, Read, Admit, Erase, type});
        receipt = q.get(); Tree(); return q;
    }
    void Add(A node, A wrapper, A object) { Wrapper(wrapper, object); nodes[node] = wrapper; Tree(); }
};
void Start(Memory& m, Q& q, bool baseline = false) {
    if (baseline) { m.Add(node0, pool, other); }
    assert(q.Prepare(queue, {pool, 16, baseline ? 1U : 0U}, &render, 1, 7));
    assert(q.Enter());
}
void NormalAndRebalance() {
    Memory m; auto q = m.Make(); m.Add(node0, pool, other);
    const A renders[]{render, render2};
    assert(q->Prepare(queue, {pool, 16, 1}, renders, 2, 7)); assert(q->Enter());
    // The first private node is the new tree root with two children. Retiring it
    // changes every relevant edge; the next erase must use a fresh traversal.
    m.Add(node1, pool + 32, render); m.Add(node2, pool + 64, render2);
    assert(q->Complete({pool, 16, 3})); assert(q->SubmittedCount() == 2);
    assert(!q->ReleaseAllowed()); assert(!q->Retire(8)); assert(m.erases == 0);
    m.reenter_erase = true;
    assert(q->Retire(7)); assert(q->ReleaseAllowed()); assert(m.erases == 2);
    assert(m.nodes.size() == 1 && m.nodes[node0] == pool);
    assert(!q->Retire(7) && m.erases == 2);
}
void NoInsertionAndCancellation() {
    Memory m; auto q = m.Make();
    assert(q->Prepare(queue, {pool, 16, 0}, &render, 1, 7));
    q->CancelPrepared(); assert(q->ReleaseAllowed());
    Start(m, *q); q->CancelPrepared(); assert(!q->ReleaseAllowed());
    m.Wrapper(pool, render); // Native consumes a slot, metadata rejects insertion.
    assert(q->Complete({pool, 16, 1})); assert(q->ReleaseAllowed()); assert(!m.erases);
    Start(m, *q); assert(q->Complete({pool, 16, 0})); assert(q->ReleaseAllowed());
}
void FailedErases() {
    for (int mode = 0; mode != 4; ++mode) {
        Memory m; auto q = m.Make(); Start(m, *q, true);
        m.Add(node1, pool + 32, render); assert(q->Complete({pool, 16, 2}));
        m.fail_erase = mode == 0; m.fail_after_erase = mode == 1;
        m.invalidate_erase = mode == 2; m.damage_erase = mode == 3;
        assert(!q->Retire(7)); assert(q->CurrentState() == Q::State::quarantined);
        assert(!q->ReleaseAllowed()); assert(!q->Retire(7)); assert(m.erases == 1);
        assert(!q->Prepare(queue, {pool, 16, 2}, &render, 1, 8));
    }
}
void InvalidBeforeEntry() {
    for (int mode = 0; mode != 11; ++mode) {
        Memory m; auto q = m.Make(); m.Add(node0, pool, other);
        if (mode == 0) { m.Put(queue + 4, A{Q::kMaxNodes + 1}); }
        if (mode == 1) { m.Put(node0 + 4, node0); }
        if (mode == 2) { m.Put(node0 + 8, node0); }
        if (mode == 3) { m.Put(head + 8, head); }
        if (mode == 4) { m.Put(node0, A{0}); }
        if (mode == 5) { m.Put(node0, A{2}); }
        if (mode == 6) { m.Put(node0 + 16, A{1}); }
        if (mode == 7) { m.changed_read = node0; }
        if (mode == 8) { m.admitted = false; }
        if (mode == 9) { m.Put(queue + 4, A{0}); }
        if (mode == 10) { m.Wrapper(pool, render); }
        assert(!q->Prepare(queue, {pool, 16, 1}, &render, 1, 7));
        assert(q->ReleaseAllowed() == (mode != 10)); assert(!m.erases);
    }
}
void InvalidAfterEntry() {
    for (int mode = 0; mode != 11; ++mode) {
        Memory m; auto q = m.Make(); Start(m, *q, true);
        m.Add(node1, pool + 32, render);
        Q::Pool after{pool, 16, 2};
        if (mode == 0) { after.begin += 32; }
        if (mode == 1) { after.capacity = 17; }
        if (mode == 2) { after.used = 0; }
        if (mode == 3) { after.used = 3; }
        if (mode == 4) { m.Wrapper(pool + 32, other); }
        if (mode == 5) { m.Put(pool + 32, type + 4); }
        if (mode == 6) { m.Put(node0 + 16, pool + 4); }
        if (mode == 7) { m.nodes.erase(node0); m.Tree(); }
        if (mode == 8) { m.admitted = false; }
        if (mode == 9) { m.Put(node1 + 16, pool + 64); }
        if (mode == 10) { m.Wrapper(pool, render); }
        assert(!q->Complete(after)); assert(!q->ReleaseAllowed() && !m.erases);
        assert(q->CurrentState() == Q::State::quarantined);
    }
}
void ChangedAfterDraw() {
    for (int mode = 0; mode != 6; ++mode) {
        Memory m; auto q = m.Make(); Start(m, *q, true);
        m.Add(node1, pool + 32, render); assert(q->Complete({pool, 16, 2}));
        if (mode == 0) { m.Wrapper(pool + 32, other); }
        if (mode == 1) { m.Put(node1 + 16, pool); }
        if (mode == 2) { m.nodes.erase(node1); m.Tree(); }
        if (mode == 3) { m.Add(node2, pool + 64, other); }
        if (mode == 4) { m.Put(head + 12, head); }
        if (mode == 5) { m.reads.clear(); m.changed_read = node1; }
        assert(!q->Retire(7)); assert(!q->ReleaseAllowed() && !m.erases);
    }
}
void AliasesAndBounds() {
    Memory m; auto q = m.Make(); const A duplicate[]{render, render};
    assert(!q->Prepare(queue, {pool, 16, 0}, duplicate, 2, 7));
    assert(!q->Prepare(queue, {pool, 0xffffffffU, 0}, &render, 1, 7));
    assert(!q->Prepare(queue, {pool, 16, 17}, &render, 1, 7));
    assert(!q->Prepare(queue, {pool, 16, 0}, &render, 1, 0));
    const A renders[]{render, render2};
    assert(q->Prepare(queue, {pool, 16, 0}, renders, 2, 7)); assert(q->Enter());
    m.Add(node1, pool, render); m.Add(node2, pool + 32, render);
    assert(!q->Complete({pool, 16, 2})); assert(!q->ReleaseAllowed());
}
void TreeInvariantsAndCapacity() {
    for (int mode = 0; mode < 3; ++mode) {
        Memory m; auto q = m.Make();
        m.Add(node0, pool, other); m.Add(node1, pool + 32, other); m.Add(node2, pool + 64, other);
        if (mode == 0) { m.Put(node0, A{1}); } // unequal black height
        if (mode == 1) { m.Put(node1 + 12, node0); } // multiple ownership
        if (mode == 2) { m.Put(node0 + 8, head); } // sentinel as child
        assert(!q->Prepare(queue, {pool, 16, 3}, &render, 1, 7));
        assert(q->ReleaseAllowed() && !m.erases);
    }
    Memory m; auto q = m.Make();
    for (A i = 0; i < Q::kMaxNodes - 1; ++i) { m.nodes[node0 + i * 32] = 0x700000 + i * 32; }
    m.Tree();
    assert(q->Prepare(queue, {pool, 16, 0}, &render, 1, 7)); assert(q->Enter());
    m.Add(0x680000, pool, render); assert(q->Complete({pool, 16, 1}));
    assert(q->Retire(7) && q->ReleaseAllowed());
    m.Add(0x680000, pool, other);
    assert(!q->Prepare(queue, {pool, 16, 1}, &render, 1, 8)); // no room for a bounded receipt
    assert(q->ReleaseAllowed());
}
void PartialSubmission() {
    Memory m; auto q = m.Make(); const A renders[]{render, render2};
    assert(q->Prepare(queue, {pool, 16, 0}, renders, 2, 7)); assert(q->Enter());
    m.Wrapper(pool, render); m.Add(node2, pool + 32, render2);
    assert(q->Complete({pool, 16, 2})); assert(q->SubmittedCount() == 1);
    assert(!q->Inspect([](void* context,A,A) noexcept {
        auto& receipt=*static_cast<Q*>(context); assert(!receipt.Retire(7)); return false;
    },q.get()));
    assert(q->CurrentState()==Q::State::submitted && !q->ReleaseAllowed());
    assert(q->Retire(7)); assert(q->ReleaseAllowed() && m.erases == 1);
}
}
int main() {
    NormalAndRebalance(); NoInsertionAndCancellation(); FailedErases();
    InvalidBeforeEntry(); InvalidAfterEntry(); ChangedAfterDraw();
    AliasesAndBounds(); TreeInvariantsAndCapacity(); PartialSubmission();
}
