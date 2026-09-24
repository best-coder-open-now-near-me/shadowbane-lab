#include "furnishing_queue.h"
#include <algorithm>
#include <cstring>

namespace wonderbane::extension::furnishing {
namespace {
bool Pointer(std::uint32_t p) noexcept { return p >= 0x10000 && p < 0x7fff0000 && !(p & 3U); }
}
bool QueueReceipt::Admitted() const noexcept {
    return access_.read && access_.admit && access_.erase && Pointer(access_.wrapper_type)
        && access_.admit(access_.context);
}
bool QueueReceipt::Read(Address at, void* out, std::size_t bytes) const noexcept {
    return Pointer(at) && bytes && bytes <= 0x7fff0000U - at
        && access_.read(access_.context, at, out, bytes);
}
bool QueueReceipt::PoolValid(Pool p) const noexcept {
    return Pointer(p.begin) && p.capacity && p.used <= p.capacity
        && p.capacity <= (0x7fff0000U - p.begin) / 32U;
}
bool QueueReceipt::Private(Address p) const noexcept {
    return std::find(renders_.begin(), renders_.begin() + render_count_, p)
        != renders_.begin() + render_count_;
}
bool QueueReceipt::Wrapper(Address p, Address& render) const noexcept {
    Address type = 0;
    return Read(p, type) && type == access_.wrapper_type && Read(p + 0x1c, render);
}
bool QueueReceipt::Capture(Snapshot& s) noexcept {
    struct Header { Address head, count; } header{};
    struct Ends { Address root, first, last; } ends{};
    if (!Admitted() || !Read(queue_, header) || !Pointer(header.head)
        || header.count > kMaxNodes || !Read(header.head + 4, ends)) { return false; }
    s.head = header.head; s.count = header.count;
    s.root = ends.root; s.first = ends.first; s.last = ends.last;
    struct Pending { Address node, parent; std::size_t parent_index; bool right; };
    std::array<Pending, 64> stack{};
    std::size_t pending = 0, count = 0;
    if (s.root) { stack[pending++] = {s.root, s.head, kMaxNodes, false}; }
    while (pending) {
        const auto p = stack[--pending];
        if (count >= s.count || p.node == s.head) { return false; }
        const auto index = count++;
        auto& n = s.nodes[index]; n = {}; n.address = p.node;
        if (!Read(p.node, n.raw) || n.raw.parent != p.parent
            || (n.raw.color & 0xffU) > 1U || !Pointer(n.raw.payload)) { return false; }
        if (p.parent_index != kMaxNodes) {
            auto& parent = s.nodes[p.parent_index];
            (p.right ? parent.right : parent.left) = index;
        }
        s.order[index] = index;
        for (const bool right : {true, false}) {
            const auto child = right ? n.raw.right : n.raw.left;
            if (child) {
                if (pending == stack.size()) { return false; }
                stack[pending++] = {child, p.node, index, right};
            }
        }
    }
    if (count != s.count) { return false; }
    std::sort(s.order.begin(), s.order.begin() + count, [&s](std::size_t a, std::size_t b) {
        return s.nodes[a].address < s.nodes[b].address;
    });
    for (std::size_t i = 1; i < count; ++i) {
        if (s.nodes[s.order[i - 1]].address == s.nodes[s.order[i]].address) { return false; }
    }
    // Erase relies on native red/black invariants, not just traversable pointers.
    for (std::size_t i = count; i > 0; --i) {
        auto& n = s.nodes[i - 1];
        const auto height = [&s](std::size_t child) {
            return child == kMaxNodes ? 1U : s.nodes[child].black_height;
        };
        const auto red = [&s](std::size_t child) {
            return child != kMaxNodes && !(s.nodes[child].raw.color & 0xffU);
        };
        if (height(n.left) != height(n.right)
            || (!(n.raw.color & 0xffU) && (red(n.left) || red(n.right)))) { return false; }
        n.black_height = height(n.left) + (n.raw.color & 0xffU);
    }
    if (count && !(s.nodes[0].raw.color & 0xffU)) { return false; }
    for (const bool right : {false, true}) {
        auto endpoint = s.head;
        if (count) {
            std::size_t i = 0;
            for (;;) {
                endpoint = s.nodes[i].address;
                const auto next = right ? s.nodes[i].right : s.nodes[i].left;
                if (next == kMaxNodes) { break; }
                i = next;
            }
        }
        if (endpoint != (right ? s.last : s.first)) { return false; }
    }
    // Reverse confirmation rejects a changed node or header before any mutation.
    for (std::size_t i = count; i > 0; --i) {
        RawNode next{};
        const auto& n = s.nodes[i - 1];
        if (!Read(n.address, next) || std::memcmp(&next, &n.raw, sizeof(next))) { return false; }
    }
    Ends verify_ends{}; Header verify_header{};
    return Read(s.head + 4, verify_ends) && Read(queue_, verify_header)
        && !std::memcmp(&ends, &verify_ends, sizeof(ends))
        && !std::memcmp(&header, &verify_header, sizeof(header)) && Admitted();
}
void QueueReceipt::Reset() noexcept {
    state_ = State::idle; queue_ = 0; ticket_ = 0;
    render_count_ = receipt_count_ = 0; before_pool_ = {}; receipt_ = {};
}
bool QueueReceipt::Prepare(Address queue, Pool pool, const Address* renders,
                           std::size_t count, std::uint64_t ticket) noexcept {
    if (state_ != State::idle || !Admitted() || !Pointer(queue) || !PoolValid(pool)
        || !ticket || !renders || !count || count > kMaxRenders) { return false; }
    for (std::size_t i = 0; i < count; ++i) {
        if (!Pointer(renders[i]) || std::find(renders, renders + i, renders[i]) != renders + i) {
            return false;
        }
    }
    queue_ = queue; before_pool_ = pool; render_count_ = count; ticket_ = ticket;
    std::copy_n(renders, count, renders_.begin());
    if (!Capture(before_) || count > kMaxNodes - before_.count) { Reset(); return false; }
    // A fresh private tree must not already be queued in this frame's pool.
    for (std::size_t i = 0; i < before_.count; ++i) {
        const auto p = before_.nodes[i].raw.payload;
        if (p >= pool.begin && p < pool.begin + pool.used * 32U) {
            Address render = 0;
            if ((p - pool.begin) % 32U || !Wrapper(p, render)) { Reset(); return false; }
            if (Private(render)) { Quarantine(); return false; }
        }
    }
    state_ = State::prepared; return true;
}
bool QueueReceipt::Enter() noexcept {
    if (state_ != State::prepared || !Admitted()) { return false; }
    state_ = State::entering; return true;
}
void QueueReceipt::CancelPrepared() noexcept { if (state_ == State::prepared) { Reset(); } }
bool QueueReceipt::SameRemainder(const Snapshot& s) const noexcept {
    std::size_t before = 0;
    for (std::size_t i = 0; i < s.count; ++i) {
        const auto& node = s.nodes[s.order[i]];
        bool ours = false;
        for (std::size_t j = 0; j < receipt_count_; ++j) {
            if (!receipt_[j].removed && receipt_[j].node == node.address
                && receipt_[j].wrapper == node.raw.payload) { ours = true; break; }
        }
        if (ours) { continue; }
        if (before == before_.count) { return false; }
        const auto& old = before_.nodes[before_.order[before++]];
        if (old.address != node.address || old.raw.payload != node.raw.payload) { return false; }
    }
    return before == before_.count && s.head == before_.head;
}
bool QueueReceipt::CurrentEntries(const Snapshot& s) const noexcept {
    std::size_t active = 0;
    for (std::size_t i = 0; i < receipt_count_; ++i) {
        const auto& e = receipt_[i]; if (e.removed) { continue; }
        ++active; bool found = false; Address render = 0;
        for (std::size_t n = 0; n < s.count; ++n) {
            if (s.nodes[n].address == e.node && s.nodes[n].raw.payload == e.wrapper) { found = true; break; }
        }
        if (!found || !Wrapper(e.wrapper, render) || render != e.render) { return false; }
    }
    return s.count == before_.count + active && SameRemainder(s);
}
bool QueueReceipt::Complete(Pool pool) noexcept {
    if (state_ != State::entering) { return false; }
    // From this point any failed proof preserves ownership indefinitely.
    Quarantine();
    if (!Admitted() || !PoolValid(pool) || pool.begin != before_pool_.begin
        || pool.capacity != before_pool_.capacity || pool.used < before_pool_.used
        || pool.used - before_pool_.used > render_count_ || !Capture(current_)) { return false; }
    const auto first = pool.begin + before_pool_.used * 32U;
    const auto end = pool.begin + pool.used * 32U;
    for (std::size_t i = 0; i < current_.count; ++i) {
        const auto& node = current_.nodes[i]; const auto p = node.raw.payload;
        if (p < first || p >= end) {
            if (p >= pool.begin && p < pool.begin + pool.used * 32U) {
                Address render = 0;
                if ((p - pool.begin) % 32U || !Wrapper(p, render) || Private(render)) { return false; }
            }
            continue;
        }
        Address render = 0;
        if ((p - pool.begin) % 32U || !Wrapper(p, render) || !Private(render)
            || receipt_count_ == kMaxRenders) { return false; }
        for (std::size_t j = 0; j < receipt_count_; ++j) {
            if (receipt_[j].wrapper == p || receipt_[j].render == render) { return false; }
        }
        receipt_[receipt_count_++] = {node.address, p, render, false};
    }
    if (!CurrentEntries(current_) || !Admitted()) { return false; }
    if (!receipt_count_) { Reset(); return true; }
    state_ = State::submitted; return true;
}
bool QueueReceipt::Retire(std::uint64_t ticket) noexcept {
    if (state_ != State::submitted || ticket != ticket_) { return false; }
    Quarantine();
    for (std::size_t i = 0; i < receipt_count_; ++i) {
        auto& entry = receipt_[i];
        if (!Capture(current_) || !CurrentEntries(current_) || !Admitted()) { return false; }
        if (!access_.erase(access_.context, queue_, entry.node)) { return false; }
        entry.removed = true;
        if (!Capture(current_) || !CurrentEntries(current_)) { return false; }
    }
    Reset(); return true;
}
}
