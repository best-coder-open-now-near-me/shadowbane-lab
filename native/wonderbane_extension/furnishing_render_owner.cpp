#include "furnishing_render_owner.h"
#include <algorithm>

namespace wonderbane::extension::furnishing {
namespace {
bool Pointer(Address p) noexcept { return p >= 0x10000 && p < 0x7fff0000 && p % 4 == 0; }
struct Busy {
    bool& value;
    explicit Busy(bool& v) noexcept : value(v) { value = true; }
    ~Busy() { value = false; }
};
}
bool RenderOwner::Owner() const noexcept { return operations_.owner && operations_.owner(operations_.context); }
bool RenderOwner::Current() const noexcept {
    return admission_.load(std::memory_order_acquire) && Owner() && operations_.current
        && operations_.current(operations_.context, selection_);
}
bool RenderOwner::PrivateTree(bool initial) noexcept {
    std::array<Address, QueueReceipt::kMaxRenders> found{}; std::size_t count = 0;
    if (!operations_.private_tree || !operations_.private_tree(operations_.context, selection_, clone_,
        found.data(), found.size(), &count) || !count || count > found.size() || found[0] != clone_) { return false; }
    for (std::size_t i = 0; i < count; ++i) {
        if (!Pointer(found[i]) || found[i] == selection_.render
            || std::find(found.begin(), found.begin() + i, found[i]) != found.begin() + i) { return false; }
    }
    if (initial) { renders_ = found; count_ = count; return true; }
    return count_ == count && std::equal(found.begin(), found.begin() + count, renders_.begin());
}
bool RenderOwner::ClearOwned() noexcept {
    if (!Owner() || !receipt_.ReleaseAllowed() || !operations_.release) { Quarantine(); return false; }
    state_ = State::releasing;
    // Source model stays retained through private destruction, keeping shared
    // resources alive. Both releases still require the original graphics context.
    for (Address* slot : {&clone_, &model_}) {
        if (*slot && (!Owner() || state_ == State::quarantined
            || !operations_.release(operations_.context, slot) || *slot)) { Quarantine(); return false; }
        if (state_ == State::quarantined) { return false; }
    }
    selection_ = {}; renders_ = {}; count_ = 0; ticket_ = 0; state_ = State::empty; return true;
}
bool RenderOwner::Acquire(const Selection& s) noexcept {
    if (busy_ || state_ != State::empty) { return false; }
    const Busy busy(busy_); selection_ = s;
    if (!Current() || !operations_.source || !operations_.retain || !operations_.clone
        || !operations_.source(operations_.context, s) || !Current()) { selection_ = {}; return false; }
    state_ = State::acquiring;
    // Publish before AddRef: even a fault before an observable increment leaves
    // one bounded uncertain transaction, not an invitation to allocate again.
    model_ = s.model;
    if (!Pointer(model_) || !operations_.retain(operations_.context, s.model, &model_)
        || model_ != s.model || !Owner() || state_ == State::quarantined) { Quarantine(); return false; }
    if (!Current()) { ClearOwned(); return false; }
    if (!operations_.clone(operations_.context, s.render, &clone_) || !Owner()
        || state_ == State::quarantined) { Quarantine(); return false; }
    // A normal null result has no private ownership; the source retain is known.
    if (!clone_) { ClearOwned(); return false; }
    if (!Pointer(clone_) || clone_ == s.render || !PrivateTree(true) || !Owner()
        || state_ == State::quarantined) { Quarantine(); return false; }
    if (!Current()) { ClearOwned(); return false; }
    state_ = State::owned; return true;
}
bool RenderOwner::Pose(const Transform& parent) noexcept {
    if (busy_ || state_ != State::owned) { return false; }
    const Busy busy(busy_);
    if (!Current() || !ValidTransform(parent) || !receipt_.ReleaseAllowed()) { return false; }
    if (!operations_.compose || !operations_.compose(operations_.context, clone_, parent)
        || !Owner() || state_ == State::quarantined) { Quarantine(); return false; }
    return Current();
}
bool RenderOwner::Submit(Address queue, std::uint64_t ticket) noexcept {
    if (busy_ || state_ != State::owned) { return false; }
    const Busy busy(busy_); QueueReceipt::Pool pool{};
    if (!Current() || !operations_.pool || !operations_.enqueue) { return false; }
    if (!PrivateTree(false)) { Quarantine(); return false; }
    if (!Current() || !operations_.pool(operations_.context, pool)) { return false; }
    if (!receipt_.Prepare(queue, pool, renders_.data(), count_, ticket)) {
        if (!receipt_.ReleaseAllowed()) { Quarantine(); } return false;
    }
    if (!Current()) { receipt_.CancelPrepared(); return false; }
    if (!receipt_.Enter()) { if (!receipt_.ReleaseAllowed()) { Quarantine(); } return false; }
    state_ = State::submitting; ticket_ = ticket;
    if (!operations_.enqueue(operations_.context, clone_, queue) || !Owner()
        || state_ == State::quarantined || !operations_.pool(operations_.context, pool)
        || !receipt_.Complete(pool)) { Quarantine(); return false; }
    // No-insertion is a known owned state. Partial insertion is real submitted
    // ownership; it must retire even if admission/selection changed during entry.
    state_ = receipt_.ReleaseAllowed() ? State::owned : State::submitted;
    return state_ == State::submitted;
}
bool RenderOwner::Retire(std::uint64_t ticket) noexcept {
    if (busy_ || state_ != State::submitted || ticket != ticket_) { return false; }
    const Busy busy(busy_); state_ = State::retiring;
    if (!Owner() || !receipt_.Retire(ticket) || state_ == State::quarantined) { Quarantine(); return false; }
    state_ = State::owned; ticket_ = 0;
    if (!Current()) { return ClearOwned(); }
    return true;
}
bool RenderOwner::Clear() noexcept {
    if (busy_ || state_ != State::owned) { return state_ == State::empty && !busy_; }
    const Busy busy(busy_); return ClearOwned();
}
bool RenderOwner::Open() noexcept {
    if (busy_ || state_ != State::empty) { return false; }
    const Busy busy(busy_); if (!Owner()) { return false; }
    admission_.store(true, std::memory_order_release); return true;
}
void RenderOwner::InvalidateContext() noexcept {
    Close(); if (state_ != State::empty) { Quarantine(); }
}
}
